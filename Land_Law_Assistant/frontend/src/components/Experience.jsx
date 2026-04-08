import { Environment, CameraControls, ContactShadows } from "@react-three/drei";
import { useChat } from "../hooks/useChat";
import { Avatar } from "./Avatar";
import { useEffect, useRef } from "react";

export const Experience = () => {
  const { cameraZoomed } = useChat();
  const cameraControlsRef = useRef();

  const POS_X = -3.2; 
  const POS_Y = -4.0;
  const SCALE = 3.0;  
  const ROTATION_Y = 0.8;

  useEffect(() => {
    if (cameraControlsRef.current) {
      cameraControlsRef.current.setLookAt(0, 0, 10, 0, 0, 0, false);

      if (cameraZoomed) {
        cameraControlsRef.current.setLookAt(
            0, 0.5, 10, 
            0, 0.5, 0, 
            true
        );
      } else {
        const headHeight = POS_Y + (1.6 * SCALE);

        cameraControlsRef.current.setLookAt(
            POS_X + 1.2, headHeight, 4.5, 
            POS_X, headHeight - 0.2, 0, 
            true
        );
      }
    }
  }, [cameraZoomed, POS_X, POS_Y, SCALE]); 

  return (
    <>
      {/* Tắt tương tác chuột với camera */}
      <CameraControls ref={cameraControlsRef} minDistance={2} maxDistance={15} enabled={false} />
      
      {/* Ánh sáng studio */}
      <ambientLight intensity={0.8} color="#ffd1dc" />
      <directionalLight position={[-5, 5, 5]} intensity={1.5} color="#ffffff" castShadow />
      {/* Điều chỉnh đèn phụ bên phải để chiếu sáng khuôn mặt đang xoay */}
      <spotLight position={[5, 2, 5]} intensity={1.2} color="#ffb6c1" angle={0.4} penumbra={1} castShadow />
      <Environment preset="city" intensity={0.5} />

      {/* Nhóm chứa Avatar với vị trí và góc xoay mới */}
      <group position={[POS_X, POS_Y, 0]} rotation={[0, ROTATION_Y, 0]} scale={SCALE}>
        <ContactShadows opacity={0.6} scale={10} blur={2.5} far={10} color="#9d174d" />
        <Avatar />
      </group>
    </>
  );
};