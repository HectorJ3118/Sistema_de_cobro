import serial
import time

def calcular_crc(payload):
    # El CRC es la suma de (CMD + DAT1...DAT8 + ETX) mask 0xFF
    return sum(payload) & 0xFF

def enviar_cambio(ser, cantidad):
    # Denominaciones soportadas por los DAT1-DAT5 de la BoardDroid
    monedas = [10.0, 5.0, 2.0, 1.0, 0.5]
    conteo = {m: 0 for m in monedas}
    
    resto = cantidad
    for m in monedas:
        conteo[m] = int(resto // m)
        resto = round(resto % m, 2)

    # Construcción de la trama WSLinker (12 bytes)
    # STX=F1, CMD=C6, DAT1(0.5), DAT2(1), DAT3(2), DAT4(5), DAT5(10), DAT6-8=00, ETX=F2
    cmd = 0xC6
    dat1 = conteo[0.5]
    dat2 = conteo[1.0]
    dat3 = conteo[2.0]
    dat4 = conteo[5.0]
    dat5 = conteo[10.0]
    etx = 0xF2
    
    payload = [cmd, dat1, dat2, dat3, dat4, dat5, 0x00, 0x00, 0x00, etx]
    crc = calcular_crc(payload)
    
    trama = [0xF1] + payload + [crc]
    
    print(f"--- Desglose para ${cantidad} ---")
    print(f"Monedas: $10({dat5}), $5({dat4}), $2({dat3}), $1({dat2}), $0.5({dat1})")
    print(f"Enviando trama: {' '.join([hex(b).upper() for b in trama])}")
    
    ser.write(bytearray(trama))

# Configuración del puerto[cite: 1]
try:
    puerto = "COM7"  # Cambia por tu puerto detectado
    ser = serial.Serial(puerto, 115200, timeout=1)
    time.sleep(2) # Espera inicialización
    
    while True:
        user_input = input("\nIngresa la cantidad de cambio (o 'salir'): ")
        if user_input.lower() == 'salir': break
        
        try:
            monto = float(user_input)
            enviar_cambio(ser, monto)
            
            # Leer respuesta de la placa (14 bytes)[cite: 1]
            respuesta = ser.read(14)
            if respuesta:
                print(f"Respuesta de placa: {respuesta.hex().upper()}")
        except ValueError:
            print("Por favor ingresa un número válido.")

    ser.close()
except Exception as e:
    print(f"Error: {e}")