import { useRef } from "react";
import { useChat } from "../hooks/useChat";

export const UI = () => {
  const input = useRef();
  const { chat, loading, message } = useChat();

  const sendMessage = () => {
    const text = input.current.value;
    if (!loading && !message && text.trim()) {
      chat(text);
      input.current.value = "";
    }
  };

  return (
    <div className="flex items-center gap-3 w-full bg-white p-2 rounded-xl shadow-inner border border-gray-100">
      {/* Ô nhập liệu */}
      <input
        className="flex-grow w-full placeholder:text-gray-400 p-3 bg-transparent border-none outline-none text-gray-700 focus:ring-0"
        placeholder="Enter your question here..."
        ref={input}
        onKeyDown={(e) => e.key === "Enter" && sendMessage()}
        disabled={loading || message}
      />
      
      {/* Nút gửi (Icon máy bay giấy) */}
      <button
        disabled={loading || message}
        onClick={sendMessage}
        className={`bg-pink-500 hover:bg-pink-600 text-white p-3 rounded-xl transition-all flex items-center justify-center shadow-md active:scale-95 ${
          loading || message ? "opacity-50 cursor-not-allowed bg-gray-400" : ""
        }`}
      >
        {loading ? (
          /* Icon loading */
          <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        ) : (
          /* Icon gửi (Send) */
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 transform rotate-[-45deg] translate-x-[2px]">
            <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
          </svg>
        )}
      </button>
    </div>
  );
};