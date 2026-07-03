/*
 * RF-Nano Door Node  —  Node 3
 * ---------------------------------------------------------------
 * First node in the sensor network. Reads a magnetic reed switch
 * (Gebildet NC door sensor) and transmits its state over the
 * built-in nRF24L01 radio to the gateway RF-Nano.
 *
 * Behavior:
 *   - Sends a packet only when the door state CHANGES (open/closed).
 *   - Sends a periodic "heartbeat" so the gateway knows the node
 *     is still alive even when nothing is happening.
 *   - Uses the ATmega328P internal pull-up, so no external resistor.
 *
 * Wiring (reed switch):
 *   Reed wire A -> D2
 *   Reed wire B -> GND        (polarity doesn't matter; it's a switch)
 *
 * Radio: the RF-Nano's nRF24L01 is hard-wired over the SPI bus
 *        (D11/D12/D13). The CE/CSN pins depend on board version --
 *        see RADIO_CE_PIN / RADIO_CSN_PIN below. Nothing to wire.
 *
 * Library: TMRh20 "RF24"  (Arduino IDE -> Library Manager -> RF24)
 * ---------------------------------------------------------------
 */

#include <SPI.h>
#include <RF24.h>

// ---------- Config ----------
const uint8_t NODE_ID       = 3;      // this door node's ID
const uint8_t MSGTYPE_DOOR  = 1;      // 1 = door state
const int     DOOR_PIN      = 2;      // reed switch digital pin

const uint8_t RADIO_CHANNEL = 76;     // 0-125; must match gateway

// RF-Nano radio pins DEPEND ON BOARD VERSION:
//   V1.0/V2.0 (Micro-USB):  CE=10, CSN=9   <-- your board (micro-USB)
//   V3.0      (USB-C):      CE=7,  CSN=8
// If the radio check below reports "NOT connected", swap to the other pair.
const uint8_t RADIO_CE_PIN  = 10;
const uint8_t RADIO_CSN_PIN = 9;

// 5-byte pipe address the GATEWAY listens on. Must match gateway.
const uint8_t GATEWAY_ADDR[5] = { 'G','W','A','Y','1' };

const unsigned long HEARTBEAT_MS = 5UL * 60UL * 1000UL; // 5 min
const unsigned long DEBOUNCE_MS  = 25;                  // reed settle time

// Bench-test only: print current state every second so you can see the
// node is alive. Set DEBUG_TICK to false (or delete) for real deployment.
const bool          DEBUG_TICK    = true;
const unsigned long DEBUG_TICK_MS = 1000;

// ---------- Shared packet format (identical across all nodes) ----------
struct Packet {
  uint8_t nodeId;    // who sent it
  uint8_t msgType;   // how to interpret the payload
  float   value1;    // door: 0.0 = closed, 1.0 = open
  float   value2;    // unused here (0)
};

RF24 radio(RADIO_CE_PIN, RADIO_CSN_PIN);

// ---------- State ----------
int  lastStable   = -1;            // last debounced raw reading
int  lastReported = -1;            // last state we transmitted
unsigned long lastEdge      = 0;   // time of last raw change
unsigned long lastHeartbeat = 0;
unsigned long lastTick      = 0;   // bench-test print timer

void setup() {
  Serial.begin(115200);            // optional: local debug via USB
  pinMode(DOOR_PIN, INPUT_PULLUP);

  bool begun = radio.begin();
  // If this reports NOT connected, the CE/CSN pins are wrong for your
  // board version -- swap RADIO_CE_PIN / RADIO_CSN_PIN (see notes above).
  Serial.print(F("radio.begin="));
  Serial.print(begun ? F("ok") : F("FAIL"));
  Serial.print(F("  chipConnected="));
  Serial.println(radio.isChipConnected() ? F("yes") : F("NO -> check CE/CSN pins"));

  radio.setPALevel(RF24_PA_LOW);   // LOW is plenty indoors; less noise
  radio.setDataRate(RF24_1MBPS);   // must match gateway
  radio.setChannel(RADIO_CHANNEL);
  radio.setRetries(5, 15);         // auto-ack retries (delay, count)
  radio.openWritingPipe(GATEWAY_ADDR);
  radio.stopListening();           // transmitter mode

  lastStable = digitalRead(DOOR_PIN);
  Serial.println("Starting Door Sensor...");
}

void loop() {
  int raw = digitalRead(DOOR_PIN);

  // --- debounce ---
  if (raw != lastStable) {
    if (millis() - lastEdge > DEBOUNCE_MS) {
      lastStable = raw;
      lastEdge   = millis();
    }
  } else {
    lastEdge = millis();
  }

  // With INPUT_PULLUP + normally-closed switch:
  //   door CLOSED -> magnet present -> switch closed -> pin LOW
  //   door OPEN   -> magnet gone    -> switch open   -> pin HIGH
  bool doorOpen = (lastStable == HIGH);

  // --- send on change ---
  if (lastStable != lastReported) {
    sendState(doorOpen);
    lastReported  = lastStable;
    lastHeartbeat = millis();
  }

  // --- periodic heartbeat ---
  if (millis() - lastHeartbeat >= HEARTBEAT_MS) {
    sendState(doorOpen);
    lastHeartbeat = millis();
  }

  // --- bench-test tick (does not transmit, just prints) ---
  if (DEBUG_TICK && millis() - lastTick >= DEBUG_TICK_MS) {
    lastTick = millis();
    Serial.print(F("tick  raw="));
    Serial.print(lastStable);            // 0 = LOW/closed, 1 = HIGH/open
    Serial.print(F("  door="));
    Serial.println(doorOpen ? F("OPEN") : F("CLOSED"));
  }
}

void sendState(bool doorOpen) {
  Packet p;
  p.nodeId  = NODE_ID;
  p.msgType = MSGTYPE_DOOR;
  p.value1  = doorOpen ? 1.0f : 0.0f;
  p.value2  = 0.0f;

  bool ok = radio.write(&p, sizeof(p));   // returns true if acked

  Serial.print(F("node "));  Serial.print(NODE_ID);
  Serial.print(F(" door=")); Serial.print(doorOpen ? "OPEN" : "CLOSED");
  Serial.println(ok ? F(" (acked)") : F(" (no ack)"));
}
