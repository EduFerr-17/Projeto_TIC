#include <SPI.h>
#include <WiFi101.h>

// Network credentials
char ssid[] = "Arduino";
char pass[] = "Teste123";

int status = WL_IDLE_STATUS;

WiFiServer server(80);
#define SENSOR_PIN A5

#define VCC 5.0
#define VOUT_OFFSET 0.2
#define MAX_PRESSURE 50.0
#define KPA_TO_MMHG 7.5

#define MEASURE_TIME 30000       // ms
#define INTERVAL 10              // ms
#define CHUNK_SIZE 10
#define MAX_SAMPLES (MEASURE_TIME / INTERVAL)

float pressureBuffer[CHUNK_SIZE];
int bufferIndex = 0;

void setup() {
  Serial.begin(9600);
  while (!Serial);

  pinMode(SENSOR_PIN, INPUT);
  
  // Check for the WiFi module
  if (WiFi.status() == WL_NO_SHIELD) {
    Serial.println("WiFi shield not present");
    while (true);
  }

  // Attempt to connect to WiFi network
  int attempts = 0;
  while (status != WL_CONNECTED) {
    Serial.print("Attempting to connect to network: ");
    Serial.println(ssid);
    Serial.print("Attempt #");
    Serial.println(attempts + 1);
    
    // Connect to WPA/WPA2 network
    status = WiFi.begin(ssid, pass);
    
    // Wait 10 seconds for connection
    delay(10000);
    
    // Check connection status
    status = WiFi.status();
    Serial.print("Connection status: ");
    Serial.println(status);
    
    if (status == WL_CONNECTED) {
      Serial.println("Successfully connected!");
      break;
    } else if (status == WL_CONNECT_FAILED) {
      Serial.println("Connection failed - check password");
    } else if (status == WL_NO_SSID_AVAIL) {
      Serial.println("Network not found - check SSID");
    } else {
      Serial.println("Connection failed - unknown error");
    }
    
    attempts++;
  }
  
 // if (status != WL_CONNECTED) {
 //   Serial.println("Failed to connect after 10 attempts. Check your credentials and network.");
 //   Serial.println("The program will continue but WiFi features won't work.");
 // }

  // Start the web server
  server.begin();
  Serial.println("Connected to WiFi network!");
  printWiFiStatus();
}

void loop() {
  WiFiClient client = server.available();
  if (client) {
    Serial.println("Client connected");

    String request = client.readStringUntil('\r');
    Serial.println("Request: " + request);
    client.flush();

    if (request.indexOf("GET /start") != -1) {
      Serial.println("Starting data stream...");

      client.println("HTTP/1.1 200 OK");
      client.println("Content-Type: application/json");
      client.println("Connection: close");
      client.println();
      client.print("{\"pressure_data\":[");

      unsigned long startTime = millis();
      int sampleCount = 0;
      bool firstValue = true;

      //Limiting the number of measurements saved at one time, to not use to much RAM from the microcontroller
      //The data is sent in chunks, in the python application each chunk is reconected for each measurement instance

      while ((millis() - startTime < MEASURE_TIME) && sampleCount < MAX_SAMPLES) { 
        float pressure = readCuffPressure();
        pressureBuffer[bufferIndex++] = pressure;
        sampleCount++;

        if (bufferIndex == CHUNK_SIZE || sampleCount == MAX_SAMPLES || (millis() - startTime >= MEASURE_TIME)) {
          // Send the buffered chunk
          for (int i = 0; i < bufferIndex; i++) {
            if (!firstValue) {
              client.print(",");
            }
            client.print(pressureBuffer[i], 2);
            firstValue = false;
          }
          bufferIndex = 0;
        }

        delay(INTERVAL);
      }

      client.println("]}");
      Serial.println("Data stream complete.");
    } else {
      // Default response
      client.println("HTTP/1.1 200 OK");
      client.println("Content-Type: text/html");
      client.println("Connection: close");
      client.println();
      client.println("<html><body>");
      client.println("<h1>Welcome to BP Monitor</h1>");
      client.println("<p>To start measurement, go to <a href=\"/start\">/start</a></p>");
      client.println("</body></html>");
    }

    delay(1);
    client.stop();
    Serial.println("Client disconnected");
  }
}

float readCuffPressure() {
  int analogValue = analogRead(SENSOR_PIN);  //Gives value in analog, 1 to 1023
  float voltage = analogValue * (VCC / 1023.0); 
  float pressure_kPa = (voltage / VCC - VOUT_OFFSET) / 0.018; //Using the formula from the sensor datasheet
  return pressure_kPa * KPA_TO_MMHG;
}

void printWiFiStatus() {
  Serial.print("Connected to network (SSID): ");
  Serial.println(WiFi.SSID());

  IPAddress ip = WiFi.localIP();
  Serial.print("Arduino IP address: ");
  Serial.println(ip);
  Serial.print("Visit in browser: http://");
  Serial.println(ip);
  
  long rssi = WiFi.RSSI();
  Serial.print("Signal strength (RSSI): ");
  Serial.print(rssi);
  Serial.println(" dBm");
}