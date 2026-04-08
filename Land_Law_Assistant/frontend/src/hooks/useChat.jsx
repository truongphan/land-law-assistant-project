import { createContext, useContext, useEffect, useState, useRef } from "react";

const ChatContext = createContext();

const BACKEND_URL = "http://127.0.0.1:8000";

export const ChatProvider = ({ children }) => {
  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cameraZoomed, setCameraZoomed] = useState(true);

  // Audio Queue State
  const [audioQueue, setAudioQueue] = useState([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef(null);

  useEffect(() => {
    if (audioQueue.length > 0 && !isPlaying) {
      const nextChunk = audioQueue[0];
      setIsPlaying(true);
      setCameraZoomed(false);

      // 1. Gửi dữ liệu sang Avatar để mấp máy môi
      setMessage({
        lipsync: nextChunk.lipsync,
        facialExpression: nextChunk.facialExpression || "neutral",
        animation: nextChunk.animation || "Talking_1",
        audio: nextChunk.audio 
      });

      // 2. Tạo và phát Audio
      const audio = new Audio("data:audio/mp3;base64," + nextChunk.audio);
      audioRef.current = audio;
      
      audio.play().catch(e => {
        console.error("Audio play error:", e);
        // Nếu lỗi vẫn phải chạy tiếp để không kẹt hàng đợi
        setIsPlaying(false);
        setAudioQueue((prev) => prev.slice(1));
      });

      // 3. Khi phát xong -> Xóa khỏi hàng đợi -> Trigger useEffect chạy lại
      audio.onended = () => {
        setIsPlaying(false);
        setAudioQueue((prev) => prev.slice(1)); // Xóa phần tử đầu tiên
      };
    } else if (audioQueue.length === 0 && !isPlaying && !loading) {
        // Khi hết hàng đợi và không còn loading -> Về trạng thái nghỉ
        setCameraZoomed(true);
        setMessage(null);
    }
  }, [audioQueue, isPlaying, loading]);


  // --- LOGIC CHAT ---
  const chat = async (userMessage) => {
    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const response = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            message: userMessage, 
            session_id: "frontend-fixed-id" 
        }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let aiTextAccumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); 

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine) continue;

          let jsonStr = trimmedLine.replace("data: ", "");
          
          try {
            const data = JSON.parse(jsonStr);

            if (data.type === "text_chunk") {
              const prefix = aiTextAccumulated.length > 0 ? " " : "";
              aiTextAccumulated += prefix + data.text;
              
              setMessages((prev) => {
                const newArr = [...prev];
                if (newArr.length > 0) {
                    newArr[newArr.length - 1] = { 
                        role: "assistant", 
                        content: aiTextAccumulated 
                    };
                }
                return newArr;
              });
            } 
            else if (data.type === "audio_chunk") {
              setAudioQueue((prev) => [...prev, data]);
            }
            else if (data.type === "complete") {
              setLoading(false);
            }
          } catch (e) {
            // Ignore json error
          }
        }
      }
    } catch (error) {
      console.error("Chat Error:", error);
      setLoading(false);
    }
  };

  const onMessagePlayed = () => {};

  return (
    <ChatContext.Provider value={{ chat, message, messages, onMessagePlayed, loading, cameraZoomed }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => useContext(ChatContext);