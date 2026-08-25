// ============================================================
// RESENSE Force/Torque Sensor -- C/C++ Sample Library
// Mode: LEGACY (raw binary packets, 28 bytes per measurement)
// Platform: Linux / macOS (POSIX serial API)
// ============================================================
//
// The sensor continuously transmits 28-byte packets at 1 Mbit/s.
// Each packet contains 7 little-endian IEEE 754 float32 values:
//   fX, fY, fZ   (force components)
//   mX, mY, mZ   (torque components)
//   temperature  (degrees Celsius)
//
// NOTE: In legacy mode there is NO framing and NO checksum.
//       If the connection starts mid-packet, data will be misaligned.
//       Re-connecting the port resets the alignment.
//
// Build (Linux/macOS):
//   g++ -std=c++11 -o read_sensor main_legacy.cpp HexFT_Legacy.cpp
//
// Windows:
//   Replace the POSIX open/read/termios calls with the Win32 CreateFile /
//   SetCommState / ReadFile API, or use a cross-platform library such as
//   Boost.Asio or the Qt serial library.
// ============================================================
#pragma once
#include <string>
#include <cstdint>

/// Raw measurement data returned by the sensor in legacy mode.
struct SensorData {
    float fX;           ///< Force X component
    float fY;           ///< Force Y component
    float fZ;           ///< Force Z component
    float mX;           ///< Torque X component
    float mY;           ///< Torque Y component
    float mZ;           ///< Torque Z component
    float temperature;  ///< Sensor temperature (degrees C)
};

/// Minimal serial interface for the Force/Torque sensor in legacy mode.
class HexFT {
public:
    /// Open the serial port. Check isOpen() before calling readSensorData().
    /// @param serialPort  e.g. "/dev/ttyACM0" (Linux) or "/dev/tty.usbmodem1" (macOS)
    explicit HexFT(const std::string& serialPort);
    ~HexFT();

    /// Returns true if the serial port was opened successfully.
    bool isOpen() const { return _fd >= 0; }

    /// Block until one complete 28-byte packet is received and return it.
    /// Call this in a loop to continuously read sensor data.
    SensorData readSensorData();

private:
    int _fd;
};
