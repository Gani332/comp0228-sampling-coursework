// COMP0228 optical transmitter. Display setup adapted from the user's working
// Thesis/CAD/firmware/home_companion/home_companion/home_companion.ino.
// No face, voice, network, touch calibration, or motor control is included.
#include <LovyanGFX.hpp>

class OpticalDisplay : public lgfx::LGFX_Device {
  lgfx::Panel_ST7796 panel;
  lgfx::Bus_SPI bus;
public:
  OpticalDisplay() {
    auto b = bus.config();
    b.spi_host = SPI2_HOST; b.spi_mode = 0;
    b.freq_write = 20000000; b.freq_read = 8000000;
    b.spi_3wire = false; b.use_lock = true;
    b.dma_channel = SPI_DMA_CH_AUTO;
    b.pin_sclk = 12; b.pin_mosi = 11; b.pin_miso = -1; b.pin_dc = 9;
    bus.config(b); panel.setBus(&bus);
    auto p = panel.config();
    p.pin_cs = 10; p.pin_rst = 8; p.pin_busy = -1;
    p.panel_width = 320; p.panel_height = 480;
    p.memory_width = 320; p.memory_height = 480;
    p.readable = false; p.invert = false; p.rgb_order = false;
    p.bus_shared = false; panel.config(p); setPanel(&panel);
  }
};
OpticalDisplay lcd;
constexpr size_t MAX_BITS = 4096;
char input[MAX_BITS + 40];
char bits[MAX_BITS + 1];
size_t inputLength = 0, bitCount = 0, bitIndex = 0;
bool inputOverflow = false, active = false;
int currentLight = -1;
uint32_t slotUs = 200000, deadline = 0, started = 0;
uint32_t maxLateUs = 0, maxDrawUs = 0;

void light(int bit) {
  if (currentLight == bit) return;
  uint32_t before = micros();
  lcd.fillRect(120, 80, 240, 160, bit ? TFT_WHITE : TFT_BLACK);
  lcd.waitDMA();
  maxDrawUs = max(maxDrawUs, (uint32_t)(micros() - before));
  currentLight = bit;
}
void caption(const char *message) {
  lcd.fillRect(0, 265, 480, 35, TFT_BLACK);
  lcd.setTextDatum(middle_center);
  lcd.setTextSize(1); lcd.setTextColor(0x7BEF, TFT_BLACK);
  lcd.drawString(message, 240, 282);
}
void finish(bool stopped) {
  active = false;
  const uint32_t elapsed = micros() - started;
  light(0);
  caption(stopped ? "Stopped - ready" : "Finished - ready");
  Serial.printf("%s bits=%u elapsed_us=%lu max_late_us=%lu max_draw_us=%lu\n",
                stopped ? "STOPPED" : "DONE", (unsigned)bitIndex,
                (unsigned long)elapsed, (unsigned long)maxLateUs,
                (unsigned long)maxDrawUs);
}
void beginTransmission(const char *data, uint32_t milliseconds) {
  bitCount = strlen(data);
  if (milliseconds < 200 || milliseconds > 1000 || !bitCount || bitCount > MAX_BITS) {
    Serial.println("ERR use 200..1000 ms and 1..4096 bits"); return;
  }
  for (size_t i=0; i<bitCount; ++i) {
    if (data[i]!='0' && data[i]!='1') { Serial.println("ERR non-binary data"); return; }
  }
  memcpy(bits, data, bitCount+1);
  slotUs = milliseconds * 1000; bitIndex = 0;
  maxLateUs = maxDrawUs = 0;
  light(0); caption("Sending - keep the camera still");
  started = deadline = micros() + 200000; // Brief serial-ACK lead time.
  active = true;
  Serial.printf("START bits=%u bit_ms=%lu\n", (unsigned)bitCount, (unsigned long)milliseconds);
}
void command(char *line) {
  if (!strcmp(line,"ID?") || !strcmp(line,"STATUS?")) {
    Serial.printf("OPTICAL:1 board=ESP32-S3 display=ST7796S busy=%d max_bits=4096 min_bit_ms=200\n", active);
    return;
  }
  if (!strcmp(line,"STOP")) {
    if (active) finish(true); else { light(0); caption("Ready"); Serial.println("OK STOP"); }
    return;
  }
  if (active) { Serial.println("ERR busy - use STOP first"); return; }
  if (!strcmp(line,"WHITE") || !strcmp(line,"BLACK")) {
    light(!strcmp(line,"WHITE")); Serial.println("OK LIGHT"); return;
  }
  if (!strcmp(line,"BLINK")) { beginTransmission("101010",1000); return; }
  if (!strncmp(line,"SEND ",5)) {
    char *end = nullptr;
    unsigned long ms = strtoul(line+5,&end,10);
    if (end==line+5 || *end!=' ' || ms<200 || ms>1000) { Serial.println("ERR SEND syntax"); return; }
    beginTransmission(end+1,ms); return;
  }
  Serial.println("ERR commands: ID? STATUS? WHITE BLACK BLINK SEND <ms> <bits> STOP");
}
void setup() {
  Serial.begin(115200);
  pinMode(10,OUTPUT); digitalWrite(10,HIGH);
  pinMode(15,OUTPUT); digitalWrite(15,HIGH); // Keep the existing touch chip deselected.
  lcd.init(); lcd.setRotation(1); lcd.setColorDepth(16);
  lcd.fillScreen(TFT_BLACK);
  lcd.setTextDatum(middle_center); lcd.setTextColor(0x7BEF,TFT_BLACK);
  lcd.drawString("COMP0228  |  LIGHT LINK",240,32);
  lcd.drawRect(116,76,248,168,0x39E7);
  light(0); caption("Ready - use the notebook");
  Serial.println("OPTICAL:1");
}
void loop() {
  // Work in small chunks so a long serial command cannot delay a light slot.
  for (int i=0; i<64 && Serial.available(); ++i) {
    const char c=Serial.read();
    if (c=='\r') continue;
    if (c=='\n') {
      input[inputLength]=0;
      if (inputOverflow) Serial.println("ERR command too long");
      else if (inputLength) command(input);
      inputLength=0; inputOverflow=false;
    } else if (inputLength < sizeof(input)-1) input[inputLength++]=c;
    else inputOverflow=true;
  }
  if (active && (int32_t)(micros()-deadline)>=0) {
    uint32_t lateness=micros()-deadline;
    maxLateUs=max(maxLateUs,lateness);
    if (lateness > slotUs/4) {
      Serial.println("ERR timing overrun"); finish(true);
    } else if (bitIndex == bitCount) finish(false);
    else {
      light(bits[bitIndex++]=='1');
      deadline += slotUs; // Absolute deadlines: drawing time does not accumulate.
      if (maxDrawUs > slotUs/2) {
        Serial.println("ERR display too slow for chosen slots"); finish(true);
      }
    }
  }
  delay(1);
}
