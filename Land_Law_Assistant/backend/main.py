import asyncio
import os
import json
import subprocess
import uuid
import logging
import time
import tempfile
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional, Union
from queue import Queue
import threading
import re

# Third-party imports
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import aiofiles
import base64

# AI and ML imports
import openai
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_pinecone import PineconeVectorStore
from langgraph.graph import StateGraph
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from typing_extensions import TypedDict

# Document processing imports
import fitz
import PyPDF2
from bs4 import BeautifulSoup
import requests

# Utility imports
from langid import classify
from gtts import gTTS
from pinecone import Pinecone
from deep_translator import GoogleTranslator
from googletrans import Translator


class Config:
    """Application configuration"""
    OPENAI_API_KEY = "sk-mjYPCFdZDhgULcLGwWeqfg"
    OPENAI_BASE_URL = "https://aiportalapi.stu-platform.live/jpe"
    PINECONE_API_KEY = "pcsk_3iV67y_GP3RR5rzXu3QLtwLtsP1L9BpZN9LdPVnp8iNDyRSWL5t147DJ3NK3emL4irFCgL"
    PINECONE_INDEX_NAME = "land-law-assistant"
    
    # Namespaces
    NAMESPACE_LEGAL = "legal-documents"
    NAMESPACE_WEB = "web-crawls"
    NAMESPACE_UPLOADS = "uploaded-documents"
    
    # Directories
    UPLOAD_DIR = "uploaded_files"
    AUDIO_DIR = "audios"
    DOCUMENTS_DIR = "documents"
    
    # Text processing
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    MAX_AUDIO_CHUNK_SIZE = 150

def setup_logging():
    """Configure application logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('legal_agent.log'),
            logging.StreamHandler()
        ]
    )
    
    # Create specialized loggers
    loggers = {
        'main': logging.getLogger(__name__),
        'workflow': logging.getLogger('workflow'),
        'tools': logging.getLogger('tools'),
        'retrieval': logging.getLogger('retrieval'),
        'web_crawler': logging.getLogger('web_crawler'),
        'classification': logging.getLogger('classification'),
        'audio': logging.getLogger('audio')
    }
    
    return loggers

LOGGERS = setup_logging()

class AgentState(TypedDict):
    """State definition for the legal agent workflow"""
    messages: List[Union[HumanMessage, AIMessage, SystemMessage]]
    user_query: str
    retrieved_docs: str
    web_crawl_docs: str
    requires_web_crawl: bool
    is_legal_query: bool
    final_response: str
    chat_history: List[Dict[str, str]]

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    sources: List[str] = []
    session_id: str

class ProcessRequest(BaseModel):
    fileName: str

class ProcessResponse(BaseModel):
    message: str
    data: Optional[dict] = None
    chunks_created: Optional[int] = None
    status: str

class UploadResponse(BaseModel):
    id: str
    url: str
    message: str
    filename: str
    size: int

class LanguageUtils:
    """Utility class for language detection and translation"""
    
    def __init__(self):
        self.translator = Translator()
    
    @staticmethod
    def detect_language(text: str) -> str:
        """Detect language of text"""
        try:
            lang, _ = classify(text)
            return lang
        except Exception as e:
            LOGGERS['main'].error(f"Language detection error: {e}")
            return 'en'  # Default to English
    
    def translate_text(self, text: str, target_lang: str) -> str:
        """Translate text to target language"""
        try:
            source_lang = self.detect_language(text)
            if source_lang == target_lang:
                return text
            
            translated = GoogleTranslator(
                source=source_lang, 
                target=target_lang
            ).translate(text)
            return translated
        except Exception as e:
            LOGGERS['main'].error(f"Translation error: {e}")
            return text


class TextProcessor:
    """Text processing utilities"""
    
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=Config.CHUNK_SIZE,
            chunk_overlap=Config.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
    
    def split_text_into_chunks(self, text: str, max_chunk_size: int = None) -> List[str]:
        """Split text into chunks suitable for processing"""
        max_size = max_chunk_size or Config.MAX_AUDIO_CHUNK_SIZE
        sentences = re.split(r'[.!?]+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            if len(current_chunk) + len(sentence) > max_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    # Handle very long sentences
                    words = sentence.split()
                    for word in words:
                        if len(current_chunk) + len(word) > max_size:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = word
                            else:
                                chunks.append(word)
                        else:
                            current_chunk += " " + word if current_chunk else word
            else:
                current_chunk += ". " + sentence if current_chunk else sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

class AIClients:
    """Centralized AI client configuration"""
    
    def __init__(self):
        self.direct_client = openai.OpenAI(
            base_url=Config.OPENAI_BASE_URL,
            api_key=Config.OPENAI_API_KEY
        )
        
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key="sk-LmOjVCDsiiCB6U3_KUmlVg",
            openai_api_base=Config.OPENAI_BASE_URL,
            dimensions=1024
        )
        
        self.llm = ChatOpenAI(
            model="GPT-4o-mini",
            openai_api_key=Config.OPENAI_API_KEY,
            openai_api_base=Config.OPENAI_BASE_URL,
            temperature=0.3
        )

class VectorStoreManager:
    """Manage Pinecone vector stores"""
    
    def __init__(self, embeddings):
        self.pc = Pinecone(api_key=Config.PINECONE_API_KEY)
        self.index = self.pc.Index(Config.PINECONE_INDEX_NAME)
        
        # Initialize vector stores
        self.web_vector_store = PineconeVectorStore(
            index=self.index,
            embedding=embeddings,
            namespace=Config.NAMESPACE_WEB,
            text_key="text"
        )
        
        self.uploads_vector_store = PineconeVectorStore(
            index=self.index,
            embedding=embeddings,
            namespace=Config.NAMESPACE_UPLOADS,
            text_key="text"
        )

class AudioGenerator:
    """Handle audio generation and lip sync"""
    
    def __init__(self, language_utils: LanguageUtils):
        self.language_utils = language_utils
        os.makedirs(Config.AUDIO_DIR, exist_ok=True)
    
    def _clean_text_for_audio(self, text: str) -> str:
        text = text.replace("*", "")
        text = text.replace("#", "")
        text = re.sub(r'^\s*-\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        
        return text.strip()

    def generate_gtts_audio(self, text: str) -> Dict[str, Any]:
        """Generate audio using Google Text-to-Speech"""
        try:
            lang = self.language_utils.detect_language(text)
            tts = gTTS(text=text, lang=lang, slow=False)
            audio_path = os.path.join(Config.AUDIO_DIR, "test.mp3")
            tts.save(audio_path)
            
            with open(audio_path, "rb") as f:
                audio_base64 = base64.b64encode(f.read()).decode()
            
            return {
                "audio": audio_base64,
                "lipsync": self._generate_basic_lipsync(text),
                "facialExpression": self._detect_emotion(text),
                "animation": "Talking_1"
            }
                
        except Exception as e:
            LOGGERS['audio'].error(f"gTTS audio generation error: {e}")
            return {
                "audio": None,
                "lipsync": self._generate_basic_lipsync(text),
                "facialExpression": "neutral",
                "animation": "Talking_1"
            }
    
    def _generate_basic_lipsync(self, text: str) -> Dict[str, Any]:
        """Generate basic lipsync data based on text phonetics"""
        words = text.split()
        duration_per_word = 0.5
        
        mouth_shapes = {
            'a': 'A', 'e': 'E', 'i': 'I', 'o': 'O', 'u': 'U',
            'default': 'neutral'
        }
        
        lipsync_data = {
            "mouthCues": [],
            "duration": len(words) * duration_per_word
        }
        
        current_time = 0
        for word in words:
            vowels = [char for char in word.lower() if char in 'aeiou']
            mouth_shape = mouth_shapes.get(vowels[0], 'neutral') if vowels else 'neutral'
            
            lipsync_data["mouthCues"].append({
                "start": current_time,
                "end": current_time + duration_per_word,
                "value": mouth_shape
            })
            current_time += duration_per_word
        
        return lipsync_data
    
    def _detect_emotion(self, text: str) -> str:
        """Detect emotion from text for facial expressions"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['sorry', 'apologize', 'unfortunately']):
            return "sad"
        elif any(word in text_lower for word in ['congratulations', 'great', 'excellent']):
            return "happy"
        elif any(word in text_lower for word in ['warning', 'careful', 'danger']):
            return "concerned"
        else:
            return "neutral"
    
    def generate_tts_chunk(self, text: str, language: str, chunk_id: str) -> Dict[str, Any]:
        """Generate TTS for a text chunk with lip sync"""
        
        clean_text = self._clean_text_for_audio(text)
        
        if not clean_text:
             return {
                "audio": None,
                "lipsync": self._generate_basic_lipsync("")
            }

        try:
            tts = gTTS(text=clean_text, lang=language, slow=False)
            
            audio_path = os.path.join(Config.AUDIO_DIR, f"{chunk_id}.mp3")
            tts.save(audio_path)
            
            self._exec_command(f"ffmpeg -y -i {audio_path} {audio_path.replace('.mp3', '.wav')}")
            
            with open(audio_path, "rb") as f:
                audio_base64 = base64.b64encode(f.read()).decode()
            
            return {
                "audio": audio_base64,
                "lipsync": self._generate_basic_lipsync(clean_text) 
            }
        except Exception as e:
            LOGGERS['audio'].error(f"TTS chunk generation error: {e}")
            return {
                "audio": None,
                "lipsync": self._generate_basic_lipsync(text)
            }
    
    def _exec_command(self, command: str) -> str:
        """Execute shell command"""
        try:
            result = subprocess.run(
                command, shell=True, stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"Command failed: {result.stderr}")
            return result.stdout
        except Exception as e:
            LOGGERS['audio'].error(f"Command execution error: {e}")
            return ""


class WebCrawler:
    """Handle web crawling for legal documents"""
    
    def __init__(self, ai_client, language_utils: LanguageUtils, text_processor: TextProcessor):
        self.ai_client = ai_client
        self.language_utils = language_utils
        self.text_processor = text_processor
        os.makedirs(Config.DOCUMENTS_DIR, exist_ok=True)
    
    def extract_text_from_pdf_url(self, url: str) -> str:
        """Extract text from PDF URL"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            pdf_path = os.path.join(Config.DOCUMENTS_DIR, "downloaded_file.pdf")
            with open(pdf_path, "wb") as f:
                f.write(response.content)
            
            doc = fitz.open(pdf_path)
            text_content = ""
            for page in doc:
                text_content += page.get_text()
            doc.close()
            
            return text_content
        except Exception as e:
            LOGGERS['web_crawler'].error(f"PDF extraction error: {e}")
            return ""
    
    def search_legal_documents(self, search_keyword: str) -> Dict[str, List[str]]:
        """Search for legal documents on government website"""
        base_url = "https://chinhphu.vn/?pageid=41852&mode=0"
        session = requests.Session()
        
        try:
            # Get initial page
            initial_response = session.get(base_url)
            soup = BeautifulSoup(initial_response.text, 'html.parser')
            
            # Prepare search payload
            payload = {
                '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'})['value'],
                '__VIEWSTATEGENERATOR': 'CA0B0334',
                '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'})['value'],
                'ctrl_191017_163$txtSearchKeyword': search_keyword,
                'ctrl_191017_163$btnSearch': 'Search',
                'ctrl_191017_163$drdRecordPerPage': '50',
                'ctrl_191017_163$drdDocCategory': '0',
                'ctrl_191017_163$drdDocOrg': '0',
                'ctrl_191017_163$drdDocYear': '0'
            }
            
            # Perform search
            response = session.post(
                url=base_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": base_url
                },
                data=payload
            )
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Parse results
            return self._parse_search_results(soup)
            
        except Exception as e:
            LOGGERS['web_crawler'].error(f"Legal document search error: {e}")
            return {}
    
    def _parse_search_results(self, soup) -> Dict[str, List[str]]:
        """Parse search results from HTML"""
        result_dict = {}
        
        table = soup.find("table", {"class": "table search-result"})
        if not table:
            return result_dict

        for row in table.find_all("tr")[1:]:
            tds = row.find_all("td")
            if len(tds) < 3:
                continue
            
            third_td = tds[2]
            substract_span = third_td.find("span", class_="substract")
            if not substract_span:
                continue
            
            key = substract_span.get_text(strip=True)
            if key not in result_dict:
                result_dict[key] = []
            
            bl_doc_files = third_td.find_all("div", class_="bl-doc-file")
            for bl_doc_file in bl_doc_files:
                a_tags = bl_doc_file.find_all("a")
                for a_tag in a_tags:
                    if a_tag.has_attr("href"):
                        result_dict[key].append(a_tag["href"])
        
        return result_dict


class DocumentProcessor:
    """Handle document processing and PDF extraction"""
    
    def __init__(self, text_processor: TextProcessor):
        self.text_processor = text_processor

    async def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file using PyMuPDF (fitz) - Better for Vietnamese"""
        try:
            text = ""
            with fitz.open(pdf_path) as doc:
                for page_num, page in enumerate(doc):
                    try:
                        page_text = page.get_text()
                        if page_text:
                            text += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
                    except Exception as e:
                        LOGGERS['main'].warning(f"Error extracting text from page {page_num + 1}: {e}")
                        continue
            
            if not text.strip():
                raise ValueError("No text could be extracted from the PDF (File might be scanned image)")
            
            return text
        except Exception as e:
            LOGGERS['main'].error(f"Error extracting text from PDF: {e}")
            raise
    
    # async def extract_text_from_pdf(self, pdf_path: str) -> str:
    #     """Extract text from PDF file"""
    #     try:
    #         text = ""
    #         with open(pdf_path, 'rb') as file:
    #             pdf_reader = PyPDF2.PdfReader(file)
    #             for page_num, page in enumerate(pdf_reader.pages):
    #                 try:
    #                     page_text = page.extract_text()
    #                     if page_text:
    #                         text += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
    #                 except Exception as e:
    #                     LOGGERS['main'].warning(f"Error extracting text from page {page_num + 1}: {e}")
    #                     continue
            
    #         if not text.strip():
    #             raise ValueError("No text could be extracted from the PDF")
            
    #         return text
    #     except Exception as e:
    #         LOGGERS['main'].error(f"Error extracting text from PDF: {e}")
    #         raise


class LegalTools:
    """Legal assistant tools"""
    
    def __init__(self, vector_store_manager: VectorStoreManager, 
                 web_crawler: WebCrawler, language_utils: LanguageUtils,
                 text_processor: TextProcessor):
        self.vector_store_manager = vector_store_manager
        self.web_crawler = web_crawler
        self.language_utils = language_utils
        self.text_processor = text_processor
    
    #@tool
    def legal_knowledge_retriever(self, query: str) -> str:
        """Retrieve relevant legal documents from the uploaded documents knowledge base."""
        print(f"\n[DEBUG] >>>>> BẮT ĐẦU TÌM KIẾM <<<<<")
        print(f"[DEBUG] Câu hỏi gốc: {query}")
        
        lang = self.language_utils.detect_language(query)
        if lang == 'en':
            query = self.language_utils.translate_text(query, 'vi')
            print(f"[DEBUG] Đã dịch: {query}")
        
        try:
            namespace = Config.NAMESPACE_UPLOADS
            print(f"[DEBUG] Đang tìm trong Namespace: '{namespace}'")
            
            print("[DEBUG] Đang gọi Pinecone...")
            results = self.vector_store_manager.uploads_vector_store.similarity_search_with_score(
                query, 
                k=5, # Lấy 5 kết quả tốt nhất
                namespace=namespace
            )
            
            print(f"[DEBUG] Pinecone trả về: {len(results)} kết quả.")
            
            if len(results) == 0:
                return ''
            
            formatted_docs = []
            for i, (doc, score) in enumerate(results):
                print(f"[DEBUG] --- Kết quả #{i+1} ---")
                print(f"[DEBUG] Score: {score:.4f}") 
                print(f"[DEBUG] Nội dung đầu: {doc.page_content[:100]}...")
                
                formatted_docs.append(f"Nội dung: {doc.page_content}\nNguồn: {doc.metadata.get('source', 'Unknown')}\n")
            
            final_result = "\n" + "="*50 + "\n".join(formatted_docs) + "="*50
            print(f"[DEBUG] >>>>> KẾT THÚC TÌM KIẾM (Thành công) <<<<<\n")
            return final_result
            
        except Exception as e:
            print(f"[DEBUG] LỖI NGHIÊM TRỌNG: {str(e)}")
            return f"Lỗi truy xuất: {str(e)}"
    
    @tool
    def web_crawler_tool(self, query: str) -> str:
        """Crawl and retrieve current legal information from government websites."""
        start_time = time.time()
        LOGGERS['tools'].info("Starting web_crawler_tool")
        
        lang = self.language_utils.detect_language(query)
        query_en = self.language_utils.translate_text(query, 'en') if lang == 'vi' else query
        
        try:
            # Identify legal area
            legal_area = self._identify_legal_area(query_en)
            legal_area_vi = self.language_utils.translate_text(legal_area, 'vi')
            
            # Search for documents
            doc_links = self.web_crawler.search_legal_documents(legal_area_vi)
            if not doc_links:
                doc_links = self.web_crawler.search_legal_documents(
                    legal_area_vi.lower().removeprefix('luật')
                )
            
            if not doc_links:
                return "No relevant legal documents found on government websites."
            
            # Select most relevant law
            selected_law = self._select_relevant_law(legal_area_vi, list(doc_links.keys()))
            
            # Process PDFs
            all_text = self._process_pdf_documents(doc_links.get(selected_law, [])[:3])
            
            if all_text:
                # Store in vector database
                self._store_crawled_content(all_text, legal_area_vi)
                
                # Retrieve relevant chunks
                search_query = query if lang == 'vi' else self.language_utils.translate_text(query, 'vi')
                upload_docs = self.vector_store_manager.web_vector_store.similarity_search(search_query, k=3)
                result = "\n".join([doc.page_content for doc in upload_docs])
                result = self.language_utils.translate_text(result, 'en')
                
                execution_time = time.time() - start_time
                LOGGERS['tools'].info(f"Web crawl completed in {execution_time:.2f}s")
                return result
            
            return "No relevant content extracted from government website PDFs."
            
        except Exception as e:
            error_msg = f"Web crawling error: {str(e)}"
            LOGGERS['tools'].error(error_msg)
            return error_msg
    
    def _identify_legal_area(self, query: str) -> str:
        """Identify the relevant legal area for the query"""
        type_legal_prompt = """
        You are a legal expert. Identify the most relevant area of law for this query and respond with a concise legal field name.
        Examples:
        - "subjects eligible to purchase, rent, or hire-purchase houses" -> "real estate law"
        - "protection of marriage and family" -> "law on marriage and family"  
        - "cooperation in production and business using land use rights" -> "land law"
        
        Query: {message}
        Legal Area:"""
        
        # This would use the AI client - simplified for refactoring
        return "general law"  # Placeholder
    
    def _select_relevant_law(self, legal_area: str, available_laws: List[str]) -> str:
        """Select the most relevant law from available options"""
        # This would use AI to select - simplified for refactoring
        return available_laws[0] if available_laws else ""
    
    def _process_pdf_documents(self, pdf_urls: List[str]) -> str:
        """Process multiple PDF documents"""
        all_text = ""
        for i, url in enumerate(pdf_urls):
            LOGGERS['web_crawler'].info(f"Processing PDF {i+1}/{len(pdf_urls)}")
            text = self.web_crawler.extract_text_from_pdf_url(url)
            if text:
                all_text += f"\n\nDocument from {url}:\n{text}\n\n"
        return all_text
    
    def _store_crawled_content(self, text: str, legal_area: str):
        """Store crawled content in vector database"""
        chunks = self.text_processor.text_splitter.split_text(text)
        ids = [str(uuid.uuid4()) for _ in chunks]
        chunks = [f"[{legal_area}] {chunk} [{legal_area}]" for chunk in chunks]
        
        self.vector_store_manager.web_vector_store.add_texts(
            texts=chunks, 
            ids=ids, 
            metadatas=[{"source": "web_crawl"}] * len(chunks)
        )


class WorkflowNodes:
    """Workflow node implementations"""
    
    def __init__(self, ai_client, language_utils: LanguageUtils, legal_tools: LegalTools):
        self.ai_client = ai_client
        self.language_utils = language_utils
        self.legal_tools = legal_tools
    
    def classify_query(self, state: AgentState) -> AgentState:
        """Classify if the query is legal or not"""
        query = state["user_query"]
        
        prompt = self._get_classification_prompt(query)
        # Simplified - would use AI client
        classification = "LEGAL"  # Placeholder
        
        state["is_legal_query"] = classification == "LEGAL"
        LOGGERS['classification'].info(f"Query classified as: {classification}")
        
        return state
    
    def check_web_crawl_needed(self, state: AgentState) -> AgentState:
        """Determine if web crawling is needed"""
        if not state["is_legal_query"]:
            state["requires_web_crawl"] = False
            return state
        
        # Simplified logic - would use AI to determine
        state["requires_web_crawl"] = "web" in state["user_query"].lower()
        return state
    
    def retrieve_legal_docs(self, state: AgentState) -> AgentState:
        """Retrieve relevant legal documents"""
        print("\n[DEBUG WORKFLOW] -> Đã vào node 'retrieve_legal_docs'")
        
        if not state["is_legal_query"]:
            print("[DEBUG WORKFLOW] Không phải câu hỏi luật, bỏ qua.")
            state["retrieved_docs"] = "Not a legal query - skipping retrieval"
            return state
        
        try:
            print(f"[DEBUG WORKFLOW] Đang gọi LegalTools với query: {state['user_query']}") 
            docs = self.legal_tools.legal_knowledge_retriever(state["user_query"])
            
            print(f"[DEBUG WORKFLOW] Kết quả trả về độ dài: {len(docs)} ký tự")
            state["retrieved_docs"] = docs
            
        except Exception as e:
            print(f"[DEBUG WORKFLOW] LỖI KHI GỌI TOOL: {e}")
            state["retrieved_docs"] = f"Error retrieving documents: {str(e)}"
        
        return state
    
    def perform_web_crawl(self, state: AgentState) -> AgentState:
        """Perform web crawling if needed"""
        if not state["requires_web_crawl"]:
            state["web_crawl_docs"] = "Web crawl not required"
            return state
        
        docs = self.legal_tools.web_crawler_tool(state["user_query"])
        if docs and "No relevant" not in docs:
            state['retrieved_docs'] = docs
        else:
            state['retrieved_docs'] = ''
        
        return state
    
    # def generate_response(self, state: AgentState) -> AgentState:
    #     """Generate the final response"""
    #     if not state["is_legal_query"]:
    #         lang = self.language_utils.detect_language(state['user_query'])
    #         response = ("I'm sorry, I can only answer legal-related questions." 
    #                    if lang == 'en' else 
    #                    "Tôi rất tiếc, tôi chỉ có thể trả lời những câu hỏi liên quan đến pháp lý.")
    #         state["final_response"] = response
    #         return state
        
    #     if state['retrieved_docs'] == '':
    #         lang = self.language_utils.detect_language(state["user_query"])
    #         state['final_response'] = ("No relevant legal documents found in the knowledge base." 
    #                                  if lang == 'en' else 
    #                                  "Không tìm thấy tài liệu pháp lý có liên quan nào.")
    #         return state
        
    #     # Generate response using AI - simplified
    #     state["final_response"] = "Generated legal response based on retrieved documents."
    #     return state
    
    def generate_response(self, state: AgentState) -> AgentState:
        """Generate the final response using GPT-4o-mini"""
        if not state["is_legal_query"]:
            lang = self.language_utils.detect_language(state['user_query'])
            response = ("I'm sorry, I can only answer legal-related questions." 
                       if lang == 'en' else 
                       "Tôi rất tiếc, tôi chỉ có thể trả lời những câu hỏi liên quan đến pháp lý.")
            state["final_response"] = response
            return state
        
        if state['retrieved_docs'] == '':
            lang = self.language_utils.detect_language(state["user_query"])
            state['final_response'] = ("No relevant legal documents found in the knowledge base." 
                                     if lang == 'en' else 
                                     "Không tìm thấy tài liệu pháp lý có liên quan nào trong cơ sở dữ liệu.")
            return state
        
        try:
            # Tạo prompt template
            system_prompt = """Bạn là một Trợ lý Luật sư ảo thân thiện, chuyên nghiệp và am hiểu tường tận Luật Đất đai 2024.

            NHIỆM VỤ:
            1. Trả lời câu hỏi dựa trên Context được cung cấp.
            2. **BẮT BUỘC** phải mở đầu câu trả lời bằng cách trích dẫn nguồn cụ thể. Ví dụ: "Dựa theo Điều X, Khoản Y của Luật Đất đai 2024...", "Theo quy định tại Điều Z..."
            3. Giọng văn: Thân thiện, tư vấn rõ ràng, dễ hiểu cho người dân.

            QUY TẮC ĐỊNH DẠNG (QUAN TRỌNG):
            - Sử dụng **Markdown** để trình bày.
            - Các nhóm hoặc tiêu đề chính phải dùng `###` (Tiêu đề 3).
            - **QUAN TRỌNG:** Trước mỗi tiêu đề `###`, BẮT BUỘC phải có 2 dấu xuống dòng (\n\n) để tách đoạn.
            - Các ý nhỏ dùng gạch đầu dòng (-).
            
            Context:
            {context}
            """
            # Gọi OpenAI (đã được config trong self.ai_client)
            response = self.ai_client.chat.completions.create(
                model="GPT-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt.format(context=state['retrieved_docs'])},
                    {"role": "user", "content": state['user_query']}
                ],
                temperature=0.3, 
                max_tokens=1000
            )
            
            state["final_response"] = response.choices[0].message.content
            
        except Exception as e:
            LOGGERS['workflow'].error(f"Error generating response: {e}")
            state["final_response"] = "Xin lỗi, đã có lỗi xảy ra trong quá trình tổng hợp câu trả lời."
            
        return state
    
    def _get_classification_prompt(self, query: str) -> str:
        """Get classification prompt template"""
        return f"""
        You are a legal query classifier. Determine if the user's query is:
        1. A legitimate legal question that can be answered with legal documents
        2. A harmful, unethical, or inappropriate request
        3. A non-legal question outside the scope of legal assistance

        Respond with exactly one of: "LEGAL", "HARMFUL", or "NON-LEGAL"

        User Query: {query}
        Classification:"""

def create_workflow(workflow_nodes: WorkflowNodes) -> StateGraph:
    """Create and configure the workflow"""
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("classify_query", workflow_nodes.classify_query)
    workflow.add_node("retrieve_legal_docs", workflow_nodes.retrieve_legal_docs)
    workflow.add_node("generate_response", workflow_nodes.generate_response)
    workflow.add_node("check_web_crawl_needed", workflow_nodes.check_web_crawl_needed)
    workflow.add_node("perform_web_crawl", workflow_nodes.perform_web_crawl)
    
    # Set entry point
    workflow.set_entry_point("classify_query")
    
    # Add edges
    workflow.add_edge("classify_query", "check_web_crawl_needed")
    
    def should_crawl(state):
        return state["requires_web_crawl"]
    
    workflow.add_conditional_edges(
        "check_web_crawl_needed",
        should_crawl,
        {
            True: "perform_web_crawl",
            False: "retrieve_legal_docs"
        }
    )
    
    workflow.add_edge("retrieve_legal_docs", "generate_response")
    workflow.add_edge("perform_web_crawl", "generate_response")
    workflow.set_finish_point("generate_response")
    
    return workflow


class LegalAssistantApp:
    """Main application class"""
    
    def __init__(self):
        # Initialize directories
        self._setup_directories()
        
        # Initialize utilities
        self.language_utils = LanguageUtils()
        self.text_processor = TextProcessor()
        
        # Initialize AI clients
        self.ai_clients = AIClients()
        
        # Initialize vector stores
        self.vector_store_manager = VectorStoreManager(self.ai_clients.embeddings)
        
        # Initialize components
        self.audio_generator = AudioGenerator(self.language_utils)
        self.web_crawler = WebCrawler(
            self.ai_clients.direct_client,
            self.language_utils,
            self.text_processor
        )
        self.document_processor = DocumentProcessor(self.text_processor)
        
        # Initialize legal tools
        self.legal_tools = LegalTools(
            self.vector_store_manager,
            self.web_crawler,
            self.language_utils,
            self.text_processor
        )
        
        # Initialize workflow
        self.workflow_nodes = WorkflowNodes(
            self.ai_clients.direct_client,
            self.language_utils,
            self.legal_tools
        )
        self.legal_workflow = create_workflow(self.workflow_nodes).compile()
        
        # Processing status tracking
        self.processing_status = {}
    
    def _setup_directories(self):
        """Create necessary directories"""
        for directory in [Config.UPLOAD_DIR, Config.AUDIO_DIR, Config.DOCUMENTS_DIR]:
            os.makedirs(directory, exist_ok=True)
    
    async def stream_text_and_audio(self, user_message: str, message_id: str) -> AsyncGenerator[str, None]:
        """Stream both text and audio chunks"""
        lang = self.language_utils.detect_language(user_message)
        
        # Initialize state
        initial_state = {
            "messages": [HumanMessage(content=user_message)],
            "user_query": user_message,
            "retrieved_docs": "",
            "web_crawl_docs": "",
            "requires_web_crawl": False,
            "is_legal_query": False,
            "final_response": "",
            "chat_history": []
        }
        
        yield f"data: {json.dumps({'type': 'status', 'message': 'Processing your legal query...', 'session_id': message_id})}\n\n"
        
        # Execute workflow
        final_state = self.legal_workflow.invoke(initial_state)
        
        # Determine response
        if final_state['retrieved_docs'] == '' and final_state['requires_web_crawl'] == False:
            full_response = final_state['final_response']
        else:
            full_response = final_state.get(
                "final_response", 
                "I apologize, but I couldn't generate a response to your query." if lang == 'en' 
                else "Tôi xin lỗi nhưng tôi không thể trả lời câu hỏi của bạn."
            )
        
        # Split into chunks for streaming
        text_chunks = self.text_processor.split_text_into_chunks(full_response, max_chunk_size=20)
        
        # Generate audio in parallel
        audio_queue = Queue()
        audio_threads = []
        
        def generate_audio_worker(chunk_text: str, chunk_index: int):
            chunk_id = f"{message_id}_chunk_{chunk_index}"
            audio_data = self.audio_generator.generate_tts_chunk(chunk_text, lang, chunk_id)
            audio_queue.put((chunk_index, audio_data))
        
        # Start audio generation threads
        for i, chunk in enumerate(text_chunks):
            thread = threading.Thread(
                target=generate_audio_worker,
                args=(chunk, i)
            )
            thread.start()
            audio_threads.append(thread)
        
        # Stream chunks
        audio_cache = {}
        
        for i, chunk in enumerate(text_chunks):
            # Send text chunk
            chunk_data = {
                "type": "text_chunk",
                "text": chunk,
                "chunk_index": i,
                "total_chunks": len(text_chunks),
                "facialExpression": "neutral",
                "animation": "Thinking" if i == 0 else "Talking_1"
            }
            yield json.dumps(chunk_data) + "\n"
            
            await asyncio.sleep(0.1)
            
            # Wait for and send audio chunk
            audio_ready = False
            while not audio_ready:
                if not audio_queue.empty():
                    chunk_index, audio_data = audio_queue.get_nowait()
                    audio_cache[chunk_index] = audio_data
                
                if i in audio_cache and audio_cache[i]:
                    audio_chunk_data = {
                        "type": "audio_chunk",
                        "chunk_index": i,
                        "audio": audio_cache[i]["audio"],
                        "lipsync": audio_cache[i]["lipsync"],
                        "facialExpression": "happy",
                        "animation": "Talking_1"
                    }
                    yield json.dumps(audio_chunk_data) + "\n"
                    audio_ready = True
                else:
                    await asyncio.sleep(0.1)
        
        # Wait for all audio threads to complete
        for thread in audio_threads:
            thread.join()
        
        # Send completion message
        final_response = {
            "type": "complete",
            "text": full_response,
            "facialExpression": "smile",
            "animation": "Idle"
        }
        yield json.dumps(final_response) + "\n"
    
    async def process_pdf_background(self, file_id: str, file_path: str, filename: str):
        """Background task to process PDF file"""
        try:
            self.processing_status[file_id] = {"status": "extracting", "progress": 10}
            text = await self.document_processor.extract_text_from_pdf(file_path)
            
            self.processing_status[file_id] = {"status": "chunking", "progress": 30}
            chunks = self.text_processor.text_splitter.split_text(text)
            
            self.processing_status[file_id] = {"status": "embedding", "progress": 50}
            documents = []
            for i, chunk in enumerate(chunks):
                doc = Document(
                    page_content=f"[{filename.split('.')[0]}] {chunk} [{filename.split('.')[0]}]",
                    metadata={
                        "source": filename,
                        "file_id": file_id,
                        "chunk_id": f"{file_id}_{i}",
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "upload_timestamp": datetime.now().isoformat(),
                        "document_type": "pdf"
                    }
                )
                documents.append(doc)
            
            self.processing_status[file_id] = {"status": "saving", "progress": 70}
            
            await asyncio.to_thread(
                self.vector_store_manager.uploads_vector_store.add_documents,
                documents
            )
            
            self.processing_status[file_id] = {
                "status": "completed",
                "progress": 100,
                "chunks_created": len(chunks),
                "text_length": len(text)
            }
            
            LOGGERS['main'].info(f"Successfully processed PDF {filename} with {len(chunks)} chunks")
            
        except Exception as e:
            LOGGERS['main'].error(f"Error processing PDF {filename}: {e}")
            self.processing_status[file_id] = {
                "status": "error",
                "progress": 0,
                "error": str(e)
            }

def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(title="Legal Assistant API", version="2.0.0")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize the main application
    legal_app = LegalAssistantApp()
    
    @app.post("/chat")
    async def chat_with_streaming_audio(request: ChatRequest):
        """Chat endpoint with streaming audio and lipsync"""
        session_id = request.session_id or str(uuid.uuid4())
        return StreamingResponse(
            legal_app.stream_text_and_audio(request.message, session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            }
        )
    
    @app.post("/upload", response_model=UploadResponse)
    async def upload_file(file: UploadFile = File(...)):
        """Upload PDF file endpoint"""
        try:
            if not file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail="Only PDF files are allowed")
            
            if file.content_type != 'application/pdf':
                raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are accepted")
            
            file_id = str(uuid.uuid4())
            file_extension = os.path.splitext(file.filename)[1]
            safe_filename = f"{file_id}{file_extension}"
            file_path = os.path.join(Config.UPLOAD_DIR, safe_filename)
            
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            legal_app.processing_status[file_id] = {"status": "uploaded", "progress": 0}
            
            LOGGERS['main'].info(f"Successfully uploaded file: {file.filename} (ID: {file_id})")
            
            return UploadResponse(
                id=file_id,
                url=file_path,
                message="File uploaded successfully",
                filename=file.filename,
                size=len(content)
            )
            
        except HTTPException:
            raise
        except Exception as e:
            LOGGERS['main'].error(f"Error uploading file: {e}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    @app.post("/process/{file_id}", response_model=ProcessResponse)
    async def process_file(file_id: str, request: ProcessRequest, background_tasks: BackgroundTasks):
        """Process uploaded PDF file endpoint"""
        try:
            if file_id not in legal_app.processing_status:
                raise HTTPException(status_code=404, detail="File not found")
            
            file_extension = ".pdf"
            safe_filename = f"{file_id}{file_extension}"
            file_path = os.path.join(Config.UPLOAD_DIR, safe_filename)
            
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="File not found on disk")
            
            background_tasks.add_task(
                legal_app.process_pdf_background,
                file_id,
                file_path,
                request.fileName
            )
            
            legal_app.processing_status[file_id] = {"status": "processing", "progress": 5}
            
            LOGGERS['main'].info(f"Started processing file: {request.fileName} (ID: {file_id})")
            
            return ProcessResponse(
                message="Processing started",
                status="processing",
                data={
                    "file_id": file_id,
                    "filename": request.fileName
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            LOGGERS['main'].error(f"Error starting file processing: {e}")
            raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
    @app.get("/process/{file_id}/status")
    async def get_processing_status(file_id: str):
        """Get processing status for a file"""
        if file_id not in legal_app.processing_status:
            raise HTTPException(status_code=404, detail="File not found")
        
        return legal_app.processing_status[file_id]
    
    @app.get("/files")
    async def list_processed_files():
        """List all processed files"""
        try:
            return {
                "files": [
                    {
                        "id": file_id,
                        "status": status
                    }
                    for file_id, status in legal_app.processing_status.items()
                ]
            }
        except Exception as e:
            LOGGERS['main'].error(f"Error listing files: {e}")
            raise HTTPException(status_code=500, detail="Failed to list files")
    
    @app.delete("/files/{file_id}")
    async def delete_file(file_id: str):
        """Delete a file and its vectors from Pinecone"""
        try:
            if file_id in legal_app.processing_status:
                del legal_app.processing_status[file_id]
            
            file_path = os.path.join(Config.UPLOAD_DIR, f"{file_id}.pdf")
            if os.path.exists(file_path):
                os.remove(file_path)
            
            return {"message": "File deleted successfully"}
            
        except Exception as e:
            LOGGERS['main'].error(f"Error deleting file: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete file")
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "pinecone_connected": True
        }
    
    # Error handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "status": "error"}
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        LOGGERS['main'].error(f"Unhandled error: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "status": "error"}
        )
    
    return app


if __name__ == "__main__":
    LOGGERS['main'].info("Starting Land Law Assistant API with Audio Support...")
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)
