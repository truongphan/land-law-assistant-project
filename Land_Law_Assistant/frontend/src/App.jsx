import { Loader } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Leva } from "leva";
import { Experience } from "./components/Experience";
import { UI } from "./components/UI";
import { ChatHistory } from "./components/ChatHistory";
import { ChatProvider } from "./hooks/useChat";

function App() {
  return (
    <ChatProvider>
      <Loader />
      <Leva hidden />
      
      <div className="fixed inset-0 z-10 pointer-events-none flex p-6 md:p-10 gap-6 md:gap-10">
        
        {/* Cột bên trái: Header & Avatar */}
        <div className="w-1/3 flex flex-col">
          <div className="glass-card bg-slate-900/95 border-slate-700 p-6 mb-6 text-center pointer-events-auto animate-fade-in-down shadow-slate-900/30">
            <h1 className="text-2xl md:text-3xl font-black text-white mb-2 tracking-wide">Land Law Assistant</h1>
            <p className="text-slate-400 text-sm md:text-base font-medium">I will always support you ❤️</p>
          </div>
        </div>

        {}
        <div className="w-2/3 h-full flex flex-col glass-card overflow-hidden pointer-events-auto animate-fade-in-up shadow-2xl border-0">
          
          {}
          <div className="p-5 bg-slate-800 border-b border-slate-700 shrink-0">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              Chat History
            </h2>
          </div>
          
          {}
          <div className="flex-grow overflow-hidden relative bg-slate-50">
            <ChatHistory />
          </div>

          {}
          <div className="p-5 bg-white border-t border-slate-200 shrink-0">
            <UI />
          </div>
        </div>
      </div>
      
      <Canvas shadows camera={{ position: [0, 0, 8], fov: 35 }} className="fixed inset-0 pointer-events-none">
        <Experience />
      </Canvas>
    </ChatProvider>
  );
}

export default App;