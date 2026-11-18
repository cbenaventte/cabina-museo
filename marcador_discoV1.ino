// Lector de disco y gancho para teléfono de disco -> PC por Serial
// Envía: GANCHO:LEVANTADO | GANCHO:COLGADO | MARCADO:<0-9>
//
// Cableado (cada interruptor entre el pin y GND, se usan pull-ups internos):
//   D2 = contacto de pulsos del disco
//   D3 = contacto "off-normal" del disco (se cierra mientras el disco está girado)
//   D4 = gancho (hook switch)
//
// POLARIDAD: verifica con multímetro y ajusta estas constantes si tu teléfono es distinto.
const bool GANCHO_LEVANTADO = LOW;   // nivel del pin cuando el auricular está levantado
const bool DISCO_FUERA_REPOSO = HIGH; // D3: en reposo cerrado a GND (LOW); al girar se abre (HIGH)
const bool PULSO_ABIERTO = LOW;      // D2: en reposo abierto; cada pulso lo cierra a GND (LOW). (El nombre es histórico: es el nivel que cuenta como pulso)

const uint8_t PIN_PULSOS = 2;
const uint8_t PIN_INICIO = 3;
const uint8_t PIN_GANCHO = 4;

const unsigned long DEBOUNCE_PULSOS_MS = 5;   // pulso real: ~60 ms abierto / ~40 ms cerrado
const unsigned long DEBOUNCE_INICIO_MS = 10;
const unsigned long DEBOUNCE_GANCHO_MS = 50;

// Antirrebote por estabilidad: el estado solo cambia si la lectura se mantiene estable
struct Entrada {
  uint8_t pin;
  unsigned long debounceMs;
  bool estado;
  bool ultimaLectura;
  unsigned long tCambio;
};

Entrada pulsos = {PIN_PULSOS, DEBOUNCE_PULSOS_MS, HIGH, HIGH, 0};
Entrada inicio = {PIN_INICIO, DEBOUNCE_INICIO_MS, HIGH, HIGH, 0};
Entrada gancho = {PIN_GANCHO, DEBOUNCE_GANCHO_MS, HIGH, HIGH, 0};

// Devuelve true si el estado estable cambió en esta llamada
bool actualizar(Entrada &e) {
  bool lectura = digitalRead(e.pin);
  if (lectura != e.ultimaLectura) {
    e.ultimaLectura = lectura;
    e.tCambio = millis();
  }
  if (lectura != e.estado && (millis() - e.tCambio) >= e.debounceMs) {
    e.estado = lectura;
    return true;
  }
  return false;
}

uint8_t contador = 0;
bool girando = false;

void setup() {
  Serial.begin(9600);
  pinMode(PIN_PULSOS, INPUT_PULLUP);
  pinMode(PIN_INICIO, INPUT_PULLUP);
  pinMode(PIN_GANCHO, INPUT_PULLUP);

  // Estado inicial sin generar eventos falsos
  pulsos.estado = pulsos.ultimaLectura = digitalRead(PIN_PULSOS);
  inicio.estado = inicio.ultimaLectura = digitalRead(PIN_INICIO);
  gancho.estado = gancho.ultimaLectura = digitalRead(PIN_GANCHO);
  Serial.println(gancho.estado == GANCHO_LEVANTADO ? "GANCHO:LEVANTADO" : "GANCHO:COLGADO");
}

void loop() {
  // 1. Gancho
  if (actualizar(gancho)) {
    Serial.println(gancho.estado == GANCHO_LEVANTADO ? "GANCHO:LEVANTADO" : "GANCHO:COLGADO");
  }

  // 2. Inicio/fin del giro del disco
  if (actualizar(inicio)) {
    if (inicio.estado == DISCO_FUERA_REPOSO) {
      girando = true;       // el usuario giró el disco
      contador = 0;
    } else if (girando) {
      girando = false;      // el disco volvió al reposo: dígito completo
      if (contador > 0) {
        uint8_t digito = (contador == 10) ? 0 : contador;  // 10 pulsos = 0
        if (contador <= 10) {
          Serial.print("MARCADO:");
          Serial.println(digito);
        }
      }
    }
  }

  // 3. Pulsos (solo mientras el disco regresa)
  if (actualizar(pulsos)) {
    if (girando && pulsos.estado == PULSO_ABIERTO) {
      contador++;
    }
  }
}
