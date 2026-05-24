import serial
import time

def calcular_crc(bytes_trama):
    # Suma de CMD a ETX enmascarado a 1 byte
    return sum(bytes_trama[1:-1]) & 0xFF

def leer_tubos(puerto_com):
    try:
        ser = serial.Serial(puerto_com, 115200, timeout=1)
        time.sleep(2)  # Estabilizar puerto

        # Enviar comando 0xC2 (Lectura de tubos)
        trama_lectura = [0xF1, 0xC2, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2, 0xB4]
        ser.write(bytearray(trama_lectura))

        respuesta = ser.read(14) # Esperamos 14 bytes
        print(f"Trama recibida: {respuesta.hex().upper()}")
        if len(respuesta) == 14 and respuesta[1] == 0xD2:
            print("\n" + "="*40)
            print(" INVENTARIO DE MONEDERO GRYPHON")
            print("="*40)

            # Extracción basada en tu ingeniería inversa
            monedas_1  = respuesta[4] 
            monedas_2  = respuesta[5]  
            monedas_5a = respuesta[6]  
            monedas_10 = respuesta[7]  

            # Cálculos de dinero
            total_1  = monedas_1 * 1.0
            total_2  = monedas_2 * 2.0
            total_5  = (monedas_5a ) * 5.0
            total_10 = monedas_10 * 10.0
            gran_total = total_1 + total_2 + total_5 + total_10

            print(f"[$1.00]  Cantidad: {monedas_1} \t= ${total_1:.2f}")
            print(f"[$2.00]  Cantidad: {monedas_2} \t= ${total_2:.2f}")
            print(f"[$5.00]  Cantidad: {monedas_5a} \t= ${total_5:.2f}")
            print(f"[$10.00] Cantidad: {monedas_10} \t= ${total_10:.2f}")
            print("-" * 40)
            print(f" TOTAL DISPONIBLE PARA CAMBIO: ${gran_total:.2f}")
            print("=" * 40)
            
        else:
            print("No se recibió la trama correcta o el monedero no respondió.")
            if respuesta: print(f"Trama cruda: {respuesta.hex().upper()}")

        ser.close()
    except Exception as e:
        print(f"Error en el puerto serial: {e}")

if __name__ == "__main__":
    leer_tubos('COM7') # <-- Pon aquí tu puerto