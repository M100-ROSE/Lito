import cv2
import mediapipe as mp

captura = cv2.VideoCapture(0)

if captura.isOpened() == False :
    print("não tem camera")
    
while captura.isOpened() :
    ret, frame = captura.read()
    if ret == True :
        cv2.imshow("captura", frame)

        # fecha a janela se s for pressionado
        if cv2.waitKey(25) & 0xFF == ord('s'):
            break
    else:
        break
    
captura.release()

# fecha todos os frames
cv2.destroyAllWindows()

