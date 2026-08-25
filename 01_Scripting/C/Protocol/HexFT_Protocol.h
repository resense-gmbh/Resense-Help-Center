// ============================================================
// RESENSE Force/Torque Sensor -- C/C++ Sample Library
// Mode: PROTOCOL (framed binary with CRC16-CCITT validation)
// ============================================================
//
// Frame format (all multi-byte values are little-endian):
//
//   Byte  Length    Description
//   ----  --------  ----------------------------------------
//   0     1         Start byte (0x7E)
//   1     1         Version (upper 4 bits) | Flags (lower 4)
//   2     1         Message type
//   3     1         Payload count (number of float32 values)
//   4     1         Rolling frame counter (0-255, wraps)
//   5..N  count*4   Payload: little-endian float32 values
//   N+1   2         CRC16-CCITT checksum (poly 0x1021, init 0xFFFF)
//
// Message types:
//   0x00  Measurement (7 floats):
//           fX, fY, fZ, mX, mY, mZ, temperature
//   0x01  Configuration (text payload -- not covered here)
//   0x02  Diagnostic (11 floats):
//           fX, fY, fZ, mX, mY, mZ, temperature,
//           current, raw_adc_voltage, board_temperature, board_voltage
//         sensor_voltage (V) = (raw_adc_voltage / board_voltage) * 3.3
//
// Build (Linux/macOS):
//   g++ -std=c++11 -o read_sensor main_protocol.cpp HexFT_Protocol.cpp
//
// Windows:
//   Replace the POSIX open/read/termios calls with the Win32 CreateFile /
//   SetCommState / ReadFile API, or a cross-platform library.
// ============================================================
#pragma once
#ifdef _WIN32
#include "serial_win.h"
#endif
#include <cstdint>
#include <string>

// ---------------------------------------------------------------------------
// Data structures
// ---------------------------------------------------------------------------

/// Basic F/T + temperature (message type 0, 7 float32 values).
struct SensorData {
    float fX;           ///< Force X
    float fY;           ///< Force Y
    float fZ;           ///< Force Z
    float mX;           ///< Torque X
    float mY;           ///< Torque Y
    float mZ;           ///< Torque Z
    float temperature;  ///< Sensor temperature (degrees C)
};

/// Extended diagnostics (message type 2, 11 float32 values).
struct SensorDiagnosticData : SensorData {
    float current;      ///< Sensor supply current (A)
    float voltage;      ///< Sensor supply voltage (V)  -- already converted
    float boardTemp;    ///< Electronics board temperature (degrees C)
    float boardVoltage; ///< Electronics board supply voltage (V)
};

/// Result of one decoded frame.
enum class FrameResult {
    OK,        ///< Frame decoded and CRC valid
    CRC_ERROR, ///< Frame received but CRC mismatch (re-sync and try again)
    IO_ERROR   ///< Read timeout or port closed
};

// ---------------------------------------------------------------------------
// HexFT class
// ---------------------------------------------------------------------------

class HexFT {
public:
    /// Open the serial port.  Check isOpen() before use.
    explicit HexFT(const std::string& serialPort);
    ~HexFT();
    bool isOpen() const {
#ifdef _WIN32
        return _serial && _serial->isOpen();
#else
        return _fd >= 0;
#endif
    }

    // -----------------------------------------------------------------------
    // High-level helpers -- block until one frame of the requested type arrives
    // -----------------------------------------------------------------------

    /// Read the next Measurement frame (type 0x00).
    /// Skips frames of other types.
    FrameResult readMeasurement(SensorData& out);

    /// Read the next Diagnostic frame (type 0x02).
    /// Skips frames of other types.
    FrameResult readDiagnostic(SensorDiagnosticData& out);

    // -----------------------------------------------------------------------
    // Low-level helper -- useful when you want to handle all frame types
    // -----------------------------------------------------------------------

    /// Decode one frame of any type.
    /// @param msgTypeOut  set to the message type byte on success
    /// @param floatsOut   floats parsed from the payload (up to 64 values)
    /// @param countOut    number of floats actually written to floatsOut
    FrameResult readAnyFrame(uint8_t& msgTypeOut,
                             float*   floatsOut,
                             int&     countOut);

private:
#ifdef _WIN32
    SerialWin* _serial;
#else
    int _fd;
#endif
    static constexpr uint8_t  START_BYTE = 0x7E;
    static constexpr int      MAX_COUNT  = 64;  // max payload floats

    bool     readExact(uint8_t* buf, int len) const;
    bool     syncToStartByte() const;
    uint16_t crc16Ccitt(const uint8_t* header, int hLen,
                        const uint8_t* payload, int pLen) const;
};
