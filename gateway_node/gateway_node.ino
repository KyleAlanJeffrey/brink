/*
 * RF-Nano Gateway  —  radio-to-serial bridge
 * ---------------------------------------------------------------
 * Plugs into the Raspberry Pi over USB. Listens for packets from
 * all remote nodes over the built-in nRF24L01 radio and forwards
 * each one to the Pi as a clean, line-terminated text message.
 *
 * The Pi sees this board as a serial device (CH340), typically
 *   /dev/ttyUSB0   (or /dev/ttyACM0)
 * Read it at 115200 baud, one message per line.
 *
 * Wiring: none beyond the USB cable. The radio is on-board.
 *
 * Must match every node on: channel, data rate, address, and the
 * Packet struct layout.
 *
 * Library: TMRh20 "RF24"  (Arduino IDE -> Library Manager -> RF24)
 * ---------------------------------------------------------------
 */

#include <SPI.h>
#include <RF24.h>

// ---------- Config (must match the nodes) ----------
const uint8_t RADIO_CHANNEL = 76;     // 0-125; same on every node

// RF-Nano radio pins DEPEND ON BOARD VERSION:
//   V1.0/V2.0 (Micro-USB):  CE=10, CSN=9
//   V3.0      (USB-C):      CE=7,  CSN=8
// If the radio check below reports "NOT connected", swap to the other pair.
const uint8_t RADIO_CE_PIN  = 10;
const uint8_t RADIO_CSN_PIN = 9;

// 5-byte address the nodes transmit to. Must match their GATEWAY_ADDR.
const uint8_t GATEWAY_ADDR[5] = { 'G','W','A','Y','1' };

// ---------- Shared packet format (identical across all nodes) ----------
struct Packet {
  uint8_t nodeId;    // who sent it
  uint8_t msgType;   // how to interpret the payload
  float   value1;
  float   value2;
};

// msgType registry (grow this as you add node types)
const uint8_t MSGTYPE_DOOR = 1;

RF24 radio(RADIO_CE_PIN, RADIO_CSN_PIN);

void setup() {
  Serial.begin(115200);

  bool begun = radio.begin();
  Serial.print(F("# radio.begin="));
  Serial.print(begun ? F("ok") : F("FAIL"));
  Serial.print(F(" chipConnected="));
  Serial.println(radio.isChipConnected() ? F("yes") : F("NO -> check CE/CSN pins"));

  radio.setPALevel(RF24_PA_LOW);    // must match nodes
  radio.setDataRate(RF24_1MBPS);    // must match nodes
  radio.setChannel(RADIO_CHANNEL);  // must match nodes
  radio.openReadingPipe(1, GATEWAY_ADDR);
  radio.startListening();           // receiver mode

  Serial.println(F("# gateway listening"));
}

void loop() {
  uint8_t pipe;
  if (radio.available(&pipe)) {
    Packet p;
    radio.read(&p, sizeof(p));
    forwardToPi(p);
  }
}

// Emit one parseable line per packet, e.g.:
//   node=3,type=1,door=OPEN
// Unknown types fall back to raw values so nothing is ever lost:
//   node=9,type=4,v1=21.50,v2=48.00
void forwardToPi(const Packet& p) {
  Serial.print(F("node="));  Serial.print(p.nodeId);
  Serial.print(F(",type=")); Serial.print(p.msgType);

  switch (p.msgType) {
    case MSGTYPE_DOOR:
      Serial.print(F(",door="));
      Serial.print(p.value1 > 0.5f ? F("OPEN") : F("CLOSED"));
      break;
    default:
      Serial.print(F(",v1=")); Serial.print(p.value1, 2);
      Serial.print(F(",v2=")); Serial.print(p.value2, 2);
      break;
  }
  Serial.println();
}
