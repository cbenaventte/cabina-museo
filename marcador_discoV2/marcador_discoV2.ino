// Lector de disco y gancho para teléfono de disco -> PC por Serial (versión 2)
// Envía: GANCHO:LEVANTADO | GANCHO:COLGADO | MARCADO:<0-9>
// y, para diagnóstico, líneas DEBUG:... que el programa de la PC ignora.
//
// Diferencia con la V1: el dígito NO depende de la polaridad del contacto "off-normal"
// (D3). Se cuentan los pulsos de D2 y, cuando pasan PAUSA_FIN_DIGITO_MS sin actividad
// en D2 ni en D3, se envía el dígito. Así funciona aunque D3 esté invertido o no exista.
//
// Cableado (cada interruptor entre el pin y GND, se usan pull-ups internos):
//   D2 = contacto de pulsos del disco
//   D3 = contacto "off-normal" del disco (solo para diagnóstico)
//   D4 = gancho (hook switch)

const bool GANCHO_LEVANTADO = LOW;   // nivel de D4 con el auricular levantado
const bool NIVEL_PULSO = LOW;        // nivel de D2 que cuenta como pulso (si queda al revés,
                                     // se cuenta el otro flanco: el número sale igual)

const uint8_t PIN_PULSOS = 2;
const uint8_t PIN_INICIO = 3;
const uint8_t PIN_GANCHO = 4;

const unsigned long DEBOUNCE_PULSOS_MS = 5;    // pulso real: ~60 ms abierto / ~40 ms cerrado
const unsigned long DEBOUNCE_INICIO_MS = 10;
const unsigned long DEBOUNCE_GANCHO_MS = 50;
const unsigned long PAUSA_FIN_DIGITO_MS = 300; // silencio que cierra el dígito

const bool DIAGNOSTICO = true;       // false = no envía las líneas DEBUG

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

// Antirrebote por estabilidad. Devuelve true si el estado estable cambió.
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

uint8_t contador = 0;          // pulsos del dígito en curso
uint8_t cambiosD2 = 0;         // diagnóstico: cambios de D2 en este dígito
uint8_t cambiosD3 = 0;         // diagnóstico: cambios de D3 en este dígito
bool actividad = false;
unsigned long tUltimaActividad = 0;

void enviarGancho() {
  Serial.println(gancho.estado == GANCHO_LEVANTADO ? "GANCHO:LEVANTADO" : "GANCHO:COLGADO");
}

void reiniciarDigito() {
  contador = cambiosD2 = cambiosD3 = 0;
  actividad = false;
}

void setup() {
  Serial.begin(9600);
  pinMode(PIN_PULSOS, INPUT_PULLUP);
  pinMode(PIN_INICIO, INPUT_PULLUP);
  pinMode(PIN_GANCHO, INPUT_PULLUP);

  pulsos.estado = pulsos.ultimaLectura = digitalRead(PIN_PULSOS);
  inicio.estado = inicio.ultimaLectura = digitalRead(PIN_INICIO);
  gancho.estado = gancho.ultimaLectura = digitalRead(PIN_GANCHO);
  enviarGancho();
  if (DIAGNOSTICO) {
    Serial.print("DEBUG:reposo D2=");
    Serial.print(pulsos.estado);
    Serial.print(" D3=");
    Serial.print(inicio.estado);
    Serial.print(" D4=");
    Serial.println(gancho.estado);
  }
}

void loop() {
  unsigned long ahora = millis();

  // 1. Gancho
  if (actualizar(gancho)) {
    enviarGancho();
    reiniciarDigito();
  }

  // 2. Contacto off-normal (solo diagnóstico y para saber que hay actividad)
  if (actualizar(inicio)) {
    cambiosD3++;
    actividad = true;
    tUltimaActividad = ahora;
  }

  // 3. Pulsos
  if (actualizar(pulsos)) {
    cambiosD2++;
    actividad = true;
    tUltimaActividad = ahora;
    if (pulsos.estado == NIVEL_PULSO) {
      contador++;
    }
  }

  // 4. Fin del dígito: un rato sin actividad en D2 ni D3
  if (actividad && (ahora - tUltimaActividad) >= PAUSA_FIN_DIGITO_MS) {
    if (DIAGNOSTICO) {
      Serial.print("DEBUG:pulsos=");
      Serial.print(contador);
      Serial.print(" cambiosD2=");
      Serial.print(cambiosD2);
      Serial.print(" cambiosD3=");
      Serial.print(cambiosD3);
      Serial.print(" reposo D2=");
      Serial.print(pulsos.estado);
      Serial.print(" D3=");
      Serial.println(inicio.estado);
    }
    // Solo se marca con el auricular levantado y con 1..10 pulsos (10 = 0)
    if (gancho.estado == GANCHO_LEVANTADO && contador >= 1 && contador <= 10) {
      Serial.print("MARCADO:");
      Serial.println(contador == 10 ? 0 : contador);
    }
    reiniciarDigito();
  }
}
