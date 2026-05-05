import serial
import time

def calcular_crc(payload):
    # Calcula el checksum sumando el payload y aplicando máscara de 8 bits[cite: 1]
    return sum(payload) & 0xFF

def obtener_inventario(ser):
    # Comando 0xC2: Leer valor en tubos[cite: 1]
    trama_inv = [0xF1, 0xC2, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2, 0xB4]
    ser.write(bytearray(trama_inv))
    
    respuesta = ser.read(14) # La placa responde con 14 bytes[cite: 1]
    if len(respuesta) == 14 and respuesta[1] == 0xD2:
        # Extraemos los conteos basándonos en tus pruebas empíricas del monedero
        return {
            10.0: respuesta[7], # DAT6
            5.0:  respuesta[6], # DAT5 (El monedero unifica los tubos C y F automáticamente)
            2.0:  respuesta[5], # DAT4
            1.0:  respuesta[4]  # DAT3
            # Se omite 0.50 porque el hardware no lo admite
        }
    return None

def dispensar_inteligente(ser, cambio_solicitado):
    inventario = obtener_inventario(ser)
    if not inventario:
        print("Error: No se pudo obtener el inventario del monedero.")
        return

    print(f"Inventario detectado: $10({inventario[10.0]}), $5({inventario[5.0]}), $2({inventario[2.0]}), $1({inventario[1.0]})")
    
    resto = cambio_solicitado
    entrega = {10.0: 0, 5.0: 0, 2.0: 0, 1.0: 0}
    
    # Algoritmo voraz con verificación estricta de stock
    for den in [10.0, 5.0, 2.0, 1.0]:
        while resto >= den and inventario[den] > 0:
            entrega[den] += 1
            inventario[den] -= 1
            resto = round(resto - den, 2)

    if resto > 0:
        print(f"ATENCIÓN: No hay monedas suficientes. Faltaron ${resto} por entregar.")
        # Aquí podrías agregar lógica para cancelar la venta si no hay cambio exacto

    # Construir trama 0xC6 para dar cambio[cite: 1]
    # Estructura BoardDroid: DAT1=$0.5, DAT2=$1, DAT3=$2, DAT4=$5, DAT5=$10[cite: 1]
    payload = [0xC6, 0x00, entrega[1.0], entrega[2.0], entrega[5.0], entrega[10.0], 0x00, 0x00, 0x00, 0xF2]
    crc = calcular_crc(payload)
    trama_final = [0xF1] + payload + [crc]
    
    print(f"Enviando orden de pago: {entrega}")
    ser.write(bytearray(trama_final))

# --- Ejecución Principal ---
try:
    ser = serial.Serial("COM7", 115200, timeout=1)
    time.sleep(2)
    
    while True:
        try:
            monto_str = input("\nIngrese monto de cambio a entregar (o 'salir' para terminar): ")
            if monto_str.lower() == 'salir':
                break
                
            monto = float(monto_str)
            dispensar_inteligente(ser, monto)
            
            
            res = ser.read(14)
            if res: 
                print(f"Respuesta de la placa: {res.hex().upper()}")
        except ValueError:
            print("Por favor, ingrese un número válido.")
            
    ser.close()  
except Exception as e:
    print(f"Error en el puerto serial: {e}")