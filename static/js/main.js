const socket = io();

let ventaActiva = false;
let montoACobrar = 0.0;
let montoRecibido = 0.0;
let cajeroActualId = null;

let tipoPagoActual = '';
let totalConComisionActual = 0.0;

socket.on('dinero_ingresado', function(data) {
    if(ventaActiva) {
        montoRecibido += data.valor;
        document.getElementById('displayRecibido').innerText = `$${montoRecibido.toFixed(2)}`;
        reproducirSonido(data.tipo === 'moneda' ? 'moneda' : 'exito');

        if (montoRecibido >= montoACobrar) {
            document.getElementById('btnFinalizar').disabled = false;
        }
    }
});

socket.on('inventario_actualizado', function(data) {
    document.getElementById('inv-1').innerText = data['1.0'] || 0;
    document.getElementById('inv-2').innerText = data['2.0'] || 0;
    document.getElementById('inv-5').innerText = data['5.0'] || 0;
    document.getElementById('inv-10').innerText = data['10.0'] || 0;
});


function hablar(texto) {
    if ('speechSynthesis' in window) {
        let mensaje = new SpeechSynthesisUtterance(texto);
        mensaje.lang = 'es-MX';
        mensaje.rate = 1.0;
        window.speechSynthesis.speak(mensaje);
    }
}

function reproducirSonido(tipo) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gainNode = ctx.createGain();
    
    osc.connect(gainNode);
    gainNode.connect(ctx.destination);
    
    if (tipo === 'moneda') {
       
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1200, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1600, ctx.currentTime + 0.15);
        gainNode.gain.setValueAtTime(0.5, ctx.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
        osc.start(); 
        osc.stop(ctx.currentTime + 0.15);
    } else if (tipo === 'exito') {
      
        osc.type = 'square';
        osc.frequency.setValueAtTime(800, ctx.currentTime);
        osc.frequency.setValueAtTime(1200, ctx.currentTime + 0.15);
        gainNode.gain.setValueAtTime(0.3, ctx.currentTime);
        gainNode.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.5); 
        osc.start(); 
        osc.stop(ctx.currentTime + 0.5);
    } else if (tipo === 'error') {
        
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(300, ctx.currentTime);
        gainNode.gain.setValueAtTime(0.5, ctx.currentTime);
        gainNode.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.7); 
        osc.start(); 
        osc.stop(ctx.currentTime + 0.7);
    }
}



async function notificarEstadoBackend(activa) {
    try {
        await fetch('/api/estado_venta', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({activa: activa})
        });
    } catch(e) { console.error("Error de enlace con hardware:", e); }
}

async function cargarPuertos() {
    const res = await fetch('/api/puertos');
    const data = await res.json();
    const select = document.getElementById('puertosSelect');
    select.innerHTML = '';
    data.puertos.forEach(p => {
        let opt = document.createElement('option');
        opt.value = p; opt.innerText = p;
        select.appendChild(opt);
    });
}

async function cargarVendedores() {
    const res = await fetch('/api/vendedores');
    const data = await res.json();
    const select = document.getElementById('vendedorSelect');
    select.innerHTML = '<option value="">Seleccionar cajera...</option>';
    data.vendedores.forEach(v => {
        let opt = document.createElement('option');
        opt.value = v.id; opt.innerText = v.nombre;
        select.appendChild(opt);
    });
}

async function conectarHardware() {
    const puerto = document.getElementById('puertosSelect').value;
    if(!puerto) return alert("Selecciona un puerto COM válido");
    
    const btn = document.getElementById('btnConectar');
    btn.disabled = true; btn.innerText = "Enlazando...";

    const res = await fetch('/api/conectar', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({puerto: puerto})
    });
    
    
    const data = await res.json(); 
    
    if(res.ok) {
        let status = document.getElementById('statusConexion');
        status.innerText = "Online";
        status.className = "font-bold mt-2 text-green-500 text-sm text-center";
        btn.innerText = "Listo";
        btn.className = "flex-1 bg-green-600 text-white py-2 rounded font-bold cursor-not-allowed";
        setTimeout(pedirInventario, 2000);
    } else {
        
        alert("Fallo de puerto: " + data.msg); 
        btn.disabled = false; btn.innerText = "Conectar";
    }
}

async function iniciarSesion() {
    const id = document.getElementById('vendedorSelect').value;
    const pin = document.getElementById('inputPin').value;
    if(!id || !pin) return alert("Ingresa tu PIN.");

    const res = await fetch('/api/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({vendedor_id: id, pin: pin})
    });
    const data = await res.json();

    if(res.ok) {
        cajeroActualId = data.user.id;
        document.getElementById('cajaLogin').classList.add('hidden');
        document.getElementById('cajaActivo').classList.remove('hidden');
        document.getElementById('nombreCajero').innerText = data.user.nombre;
        document.getElementById('inputPin').value = '';
        document.getElementById('bloqueadorPOS').classList.add('hidden');

        // Desactivación y congelamiento del bloque de hardware para resguardo operativo
        document.getElementById('puertosSelect').disabled = true;
        document.getElementById('btnConectar').disabled = true;
        document.getElementById('btnConectar').classList.add('opacity-40', 'cursor-not-allowed');
        document.getElementById('btnRefrescarPuertos').disabled = true;
        document.getElementById('btnRefrescarPuertos').classList.add('opacity-40');
        reproducirSonido('exito');
    } else {
        alert(data.msg); reproducirSonido('error');
    }
}

async function pedirPinAdmin(accion) {
    let pinAdmin = prompt("Introduce PIN de Administrador :");
    if (!pinAdmin) return;

    // Solo enviamos el PIN
    const res = await fetch('/api/auth_admin', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pin: pinAdmin})
    });

    if (res.ok) {
        if (accion === 'cerrar_turno') {
            cajeroActualId = null;
            document.getElementById('cajaLogin').classList.remove('hidden');
            document.getElementById('cajaActivo').classList.add('hidden');
            document.getElementById('bloqueadorPOS').classList.remove('hidden');
            
            // Reactivar controles de hardware tras cierre del turno
            document.getElementById('puertosSelect').disabled = false;
            document.getElementById('btnConectar').disabled = false;
            document.getElementById('btnConectar').classList.remove('opacity-40', 'cursor-not-allowed');
            document.getElementById('btnRefrescarPuertos').disabled = false;
            document.getElementById('btnRefrescarPuertos').classList.remove('opacity-40');
            
            await fetch('/api/logout_admin', { method: 'POST' });
            alert("Turno cerrado .");
        } 
        else if (accion === 'dashboard') {
            window.open("/dashboard", "_blank");
        }
    } else {
        const data = await res.json();
        alert(" Acceso denegado: " + (data.msg || "PIN in recto."));
        reproducirSonido('error');
    }
}

async function iniciarVenta() {
    const input = document.getElementById('inputCobro').value;
    if (input <= 0 || isNaN(input)) return alert("Monto inválido.");
    
    montoACobrar = parseFloat(input);
    montoRecibido = 0.0;
    ventaActiva = true;
    
    await notificarEstadoBackend(true);
    
    document.getElementById('inputCobro').disabled = true;
    document.getElementById('btnIniciarVenta').disabled = true;
    document.getElementById('btnCancelar').disabled = false;
    document.getElementById('btnTarjeta').disabled = false;
    document.getElementById('btnTransferencia').disabled = false;
    document.getElementById('displayRecibido').innerText = "$0.00";
    
    hablar(`El Total es de ${Math.floor(montoACobrar)} pesos.`);
}

async function cancelarVenta() {
    if (montoRecibido > 0) {
        let conf = confirm(`El usuario ya ingresó $${montoRecibido.toFixed(2)} en efectivo. ¿Deseas cancelar ?`);
        if (!conf) return;
    }
    hablar("Venta cancelada.");
    reiniciarVenta();
}

function abrirPagoAlternativo(tipo) {
    tipoPagoActual = tipo;
    let subtotal = montoACobrar;
    let comision = 0.0;

    if (tipo === 'tarjeta') {
        document.getElementById('pagoAlternativoIcono').innerText = '💳';
        document.getElementById('pagoAlternativoTitulo').innerText = 'Pago con Tarjeta';
        comision = Math.round((subtotal * 0.047) * 100) / 100;
        document.getElementById('pagoAltComision').innerText = `$${comision.toFixed(2)}`;
        document.getElementById('rowComision').classList.remove('hidden');
    } else {
        document.getElementById('pagoAlternativoIcono').innerText = '🏦';
        document.getElementById('pagoAlternativoTitulo').innerText = 'Pago por Transferencia';
        document.getElementById('rowComision').classList.add('hidden');
    }

    totalConComisionActual = Math.round((subtotal + comision) * 100) / 100;
    document.getElementById('pagoAltSubtotal').innerText = `$${subtotal.toFixed(2)}`;
    document.getElementById('pagoAltTotal').innerText = `$${totalConComisionActual}`;
    document.getElementById('modalPagoAlternativo').classList.remove('hidden');
    const formateadorMx = new Intl.NumberFormat('es-MX', {
        style: 'currency',
        currency: 'MXN'
    });

    
    let totalTextoVoz = formateadorMx.format(totalConComisionActual);

   
    if (tipo === 'tarjeta') {
        hablar(`Total con comisión: ${totalTextoVoz}`);
    } else {
        hablar(`Total a transferir: ${totalTextoVoz}`);
    }
}


function cerrarPagoAlternativoModal() {
    document.getElementById('modalPagoAlternativo').classList.add('hidden');
}

async function confirmarPagoAlternativo() {
    document.getElementById('modalPagoAlternativo').classList.add('hidden');
    hablar("Pago verificado.");
    montoRecibido = totalConComisionActual; 
    await guardarVentaBD(totalConComisionActual, tipoPagoActual);
    reiniciarVenta();
}

function esperarConfirmacionManual(billetesADar, monedasSobrantes) {
    return new Promise((resolve) => {
        const modal = document.getElementById('modalCambio');
        const contenedor = document.getElementById('contenedorBilletes');
        const btn = document.getElementById('btnConfirmarEntrega');
        
        document.getElementById('modalMonedas').innerText = `$${monedasSobrantes.toFixed(2)}`;
        contenedor.innerHTML = ''; 

        const colores = { 500: 'bg-gray-700 border-blue-400', 200: 'bg-green-800 border-green-400', 100: 'bg-red-800 border-red-400', 50: 'bg-fuchsia-800 border-fuchsia-400', 20: 'bg-blue-800 border-blue-400' };

        for (const [den, cant] of Object.entries(billetesADar)) {
            if (cant > 0) {
                contenedor.innerHTML += `
                    <div class="relative w-44 h-20 rounded-lg shadow-lg flex items-center justify-center border-2 ${colores[den]}">
                        <span class="text-3xl font-black text-white">$${den}</span>
                        <div class="absolute -top-2 -right-2 bg-orange-500 text-white rounded-full h-8 w-8 flex items-center justify-center text-sm font-bold border-2 border-gray-800">x${cant}</div>
                    </div>
                `;
            }
        }
        modal.classList.remove('hidden');
        btn.onclick = () => { modal.classList.add('hidden'); resolve(); };
    });
}

async function procesarCambio() {
    if (montoRecibido < montoACobrar) return alert("Fondos insuficientes");

    let cambioTotal = Math.round((montoRecibido - montoACobrar) * 100) / 100;
    reproducirSonido('exito');

    if (cambioTotal <= 0) {
        hablar("Cobro exacto.");
        await guardarVentaBD(montoACobrar, 'efectivo');
        reiniciarVenta();
        return;
    }

    let cambioBilletes = {};
    let resto = cambioTotal;
    const billetes = [500, 200, 100, 50, 20];
    
    for (let den of billetes) {
        if (resto >= den) {
            let cantidad = Math.floor(resto / den);
            cambioBilletes[den] = cantidad;
            resto = Math.round((resto - (cantidad * den)) * 100) / 100;
        }
    }

    let inv_temp = {
        10: parseInt(document.getElementById('inv-10').innerText) || 0,
        5: parseInt(document.getElementById('inv-5').innerText) || 0,
        2: parseInt(document.getElementById('inv-2').innerText) || 0,
        1: parseInt(document.getElementById('inv-1').innerText) || 0
    };
    let monedasDisp = {10: 0, 5: 0, 2: 0, 1: 0};
    
    for (let den of [10, 5, 2, 1]) {
        while (resto >= den && inv_temp[den] > 0) {
            monedasDisp[den]++; inv_temp[den]--;
            resto = Math.round((resto - den) * 100) / 100;
        }
    }

    if (resto > 0) return alert(`Monedas insuficientes. Faltan: $${resto.toFixed(2)}`);
    
    let totalMonedas = Object.entries(monedasDisp).reduce((acc, [den, cant]) => acc + (den * cant), 0);
    hablar(`Su cambio es de ${Math.floor(cambioTotal)} pesos.`);
    
    if (Object.keys(cambioBilletes).length > 0) {
        await esperarConfirmacionManual(cambioBilletes, totalMonedas); 
    }

    if (totalMonedas > 0) {
        try {
            await fetch('/api/dispensar', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ monto: totalMonedas })
            });
        } catch (e) { console.error("Error físico de dispensado:", e); }
    }

    await guardarVentaBD(montoACobrar, 'efectivo');
    reiniciarVenta();
}

async function guardarVentaBD(montoVendidoFinal, metodoPago) {
    if (!cajeroActualId) return;
    try {
        await fetch('/api/guardar_venta', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                monto_vendido: montoVendidoFinal,
                monto_pagado: montoRecibido,
                vendedor_id: cajeroActualId,
                metodo_pago: metodoPago
            })
        });
    } catch(e) { console.error("Fallo de base de datos", e); }
}

function reiniciarVenta() {
    ventaActiva = false; montoACobrar = 0.0; montoRecibido = 0.0;
    notificarEstadoBackend(false);
    
    const input = document.getElementById('inputCobro');
    input.disabled = false; input.value = '';
    
    document.getElementById('displayRecibido').innerText = "$0.00";
    document.getElementById('btnIniciarVenta').disabled = false;
    document.getElementById('btnFinalizar').disabled = true;
    document.getElementById('btnCancelar').disabled = true;
    document.getElementById('btnTarjeta').disabled = true;
    document.getElementById('btnTransferencia').disabled = true;
    setTimeout(pedirInventario, 2000);
}

async function pedirInventario() {
    await fetch('/api/inventario', { method: 'POST' });
}

window.onload = () => { 
    cargarPuertos(); 
    cargarVendedores(); 
    
    // Pedir inventario automáticamente al abrir la página (por si la placa ya estaba conectada)
    setTimeout(pedirInventario, 1000); 
};