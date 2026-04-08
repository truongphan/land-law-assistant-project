import { useChat } from "../hooks/useChat";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";

export const ChatHistory = () => {
  const { messages } = useChat();
  const endRef = useRef(null);
  const chatMessages = messages || [];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const formatContent = (text) => {
    if (!text) return "";
    let cleanText = text;

    cleanText = cleanText.replace(/([^\n])(###)/g, '$1\n\n$2');

    cleanText = cleanText.replace(/([^\n])(\s?-\s\*\*)/g, '$1\n\n$2');

    cleanText = cleanText.replace(/([^\n])(\s?\d+\.\s)/g, '$1\n\n$2');

    return cleanText;
  };

  return (
    <div className="h-full p-6 overflow-y-auto flex flex-col gap-6 scrollbar-hide pb-24">
      {chatMessages.length === 0 && (
        <div className="text-center text-gray-500 mt-10 italic animate-pulse">
          Xin chào, tôi có thể giúp gì về Luật Đất đai cho bạn?
        </div>
      )}

      {chatMessages.map((msg, index) => (
        <div
          key={index}
          className={`flex flex-col max-w-[90%] md:max-w-[85%] animate-slide-in ${
            msg.role === "user" ? "self-end items-end" : "self-start items-start"
          }`}
        >
          <span className={`text-xs font-bold mb-1 opacity-70 ${
              msg.role === "user" ? "text-blue-800 mr-2" : "text-gray-600 ml-2"
          }`}>
            {msg.role === "user" ? "You" : "Assistant"}
          </span>
          
          <div
            className={`p-4 rounded-2xl shadow-md text-sm md:text-base leading-relaxed ${
              msg.role === "user"
                ? "bg-gradient-to-br from-blue-600 to-blue-500 text-white rounded-br-none shadow-blue-200"
                : "bg-white/95 text-gray-800 rounded-bl-none border border-gray-100 shadow-lg backdrop-blur-sm"
            }`}
          >
            {msg.content ? (
              <div className="prose prose-sm max-w-none text-inherit dark:prose-invert">
                <ReactMarkdown 
                  remarkPlugins={[remarkGfm, remarkBreaks]} 
                  components={{
                    p: ({node, ...props}) => <p className="mb-3 last:mb-0 block" {...props} />,
                    
                    ul: ({node, ...props}) => <ul className="list-disc list-outside ml-5 mb-4 space-y-2" {...props} />,
                    ol: ({node, ...props}) => <ol className="list-decimal list-outside ml-5 mb-4 space-y-2" {...props} />,
                    
                    li: ({node, ...props}) => <li className="pl-1" {...props} />,
                    
                    a: ({node, ...props}) => <a className="text-blue-600 hover:underline font-semibold" {...props} />,
                    
                    strong: ({node, ...props}) => <span className="font-bold text-blue-700" {...props} />,
                    h3: ({node, ...props}) => <h3 className="text-lg font-bold mt-5 mb-2 text-gray-900 block border-b-2 border-blue-100 pb-1" {...props} />,
                  }}
                >
                  {/* GỌI HÀM FORMAT Ở ĐÂY */}
                  {formatContent(msg.content)}
                </ReactMarkdown>
              </div>
            ) : (
              <div className="flex gap-1 h-6 items-center px-2">
                <span className="w-2 h-2 bg-current rounded-full animate-bounce"></span>
                <span className="w-2 h-2 bg-current rounded-full animate-bounce delay-100"></span>
                <span className="w-2 h-2 bg-current rounded-full animate-bounce delay-200"></span>
              </div>
            )}
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
};