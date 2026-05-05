import serial
import time

def calcular_crc(payload):
    # Suma CMD + DATs + ETX y aplica máscara 0xFF
    return sum(payload) & 0xFF

def vaciar_monedero(puerto_com):
    try:
        ser = serial.Serial(puerto_com, 115200, timeout=2)
        time.sleep(2) # Tiempo para que el bus MDB estabilice

        # PASO 1: Leer inventario actual[cite: 1]
        # Trama 0xC2 fija para lectura de tubos[cite: 1]
        ser.write(bytearray([0xF1, 0xC2, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2, 0xB4]))
        
        respuesta = ser.read(14)
        if len(respuesta) == 14 and respuesta[1] == 0xD2:
            # Extraemos cantidades de monedas[cite: 1]
            c050 = respuesta[2] # DAT1
            c100 = respuesta[3] # DAT2
            c200 = respuesta[4] # DAT3
            c500 = respuesta[5] # DAT4
            c1000 = respuesta[6] # DAT5

            print(f"Inventario detectado: $0.50:{c050}, $1:{c100}, $2:{c200}, $5:{c500}, $10:{c1000}")
            
            if sum([c050, c100, c200, c500, c1000]) == 0:
                print("Los tubos ya están vacíos.")
                return

            # PASO 2: Enviar orden de vaciado total[cite: 1]
            print("Iniciando vaciado masivo...")
            
            # Comando 0xC6 (Enviar cantidad de monedas a dispensar)[cite: 1]
            # Ponemos las cantidades exactas que acabamos de leer[cite: 1]
            cmd = 0xC6
            etx = 0xF2
            datos_pago = [cmd, c050, c100, c200, c500, c1000, 0x00, 0x00, 0x00, etx]
            crc_pago = calcular_crc(datos_pago)
            
            trama_pago = [0xF1] + datos_pago + [crc_pago]
            ser.write(bytearray(trama_pago))

            # Esperar confirmación de la tarea CoinOut[cite: 1]
            confirmacion = ser.read(14)
            if confirmacion and confirmacion[1] == 0xD6:
                print("Orden de vaciado recibida por el monedero con éxito.")
            else:
                print("La placa no confirmó el inicio del vaciado.")
        else:
            print("No se pudo leer el inventario inicial.")

        ser.close()
    except Exception as e:
        print(f"Error de comunicación: {e}")

if __name__ == "__main__":
    vaciar_monedero('COM7') # Ajusta tu puerto aquí[cite: 1]