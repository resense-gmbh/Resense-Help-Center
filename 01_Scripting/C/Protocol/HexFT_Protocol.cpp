// HexFT_Protocol.cpp -- Implementation for protocol (framed + CRC) mode.
// See HexFT_Protocol.h for full protocol documentation.

#include "HexFT_Protocol.h"

#include <cstring>
#include <iostream>
#ifdef _WIN32
#include "serial_win.h"
#else
#include <cerrno>
#include <cstddef>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#endif

// ---------------------------------------------------------------------------
// Constructor / Destructor
// ---------------------------------------------------------------------------

HexFT::HexFT(const std::string& serialPort) {
#ifdef _WIN32
    try {
        _serial = new SerialWin(serialPort, 1000000); // 1M baud
    } catch (const std::exception& e) {
        std::cerr << "Error opening " << serialPort << ": " << e.what() << "\n";
        _serial = nullptr;
    }
#else
    _fd = open(serialPort.c_str(), O_RDWR | O_NOCTTY);
    if (_fd < 0) {
        std::cerr << "Error opening " << serialPort << ": "
                  << strerror(errno) << "\n";
        return;
    }
    struct termios tty{};
    if (tcgetattr(_fd, &tty) != 0) {
        std::cerr << "tcgetattr failed: " << strerror(errno) << "\n";
        close(_fd); _fd = -1;
        return;
    }
    cfsetispeed(&tty, B1000000);
    cfsetospeed(&tty, B1000000);
    cfmakeraw(&tty);
    tty.c_cc[VMIN]  = 1;   // block until at least 1 byte
    tty.c_cc[VTIME] = 10;  // 1-second inter-character timeout
    if (tcsetattr(_fd, TCSANOW, &tty) != 0) {
        std::cerr << "tcsetattr failed: " << strerror(errno) << "\n";
        close(_fd); _fd = -1;
    }
#endif

}

HexFT::~HexFT() {
#ifdef _WIN32
    if (_serial) delete _serial;
#else
    if (_fd >= 0) close(_fd);
#endif
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

bool HexFT::readExact(uint8_t* buf, int len) const {
    int remaining = len;
    while (remaining > 0) {
#ifdef _WIN32
        int n = _serial ? _serial->read(buf, remaining) : -1;
#else
        int n = read(_fd, buf, remaining);
#endif
        if (n <= 0) return false; // timeout or error
        buf       += n;
        remaining -= n;
    }
    return true;
}

bool HexFT::syncToStartByte() const {
    uint8_t b;
    do {
        if (!readExact(&b, 1)) return false;
    } while (b != START_BYTE);
    return true;
}

uint16_t HexFT::crc16Ccitt(const uint8_t* header, int hLen,
                             const uint8_t* payload, int pLen) const {
    uint16_t crc = 0xFFFF;

    auto process = [&](const uint8_t* data, int len) {
        for (int i = 0; i < len; ++i) {
            crc ^= static_cast<uint16_t>(data[i]) << 8;
            for (int j = 0; j < 8; ++j)
                crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
        }
    };

    process(header,  hLen);
    process(payload, pLen);
    return crc;
}

// ---------------------------------------------------------------------------
// Low-level frame decoder
// ---------------------------------------------------------------------------

FrameResult HexFT::readAnyFrame(uint8_t& msgTypeOut,
                                 float*   floatsOut,
                                 int&     countOut) {
    // 1. Synchronise to start byte
    if (!syncToStartByte()) return FrameResult::IO_ERROR;

    // 2. Read 4-byte header
    uint8_t hdr[4];
    if (!readExact(hdr, 4)) return FrameResult::IO_ERROR;

    // hdr[0] = version(7:4) | flags(3:0)
    // hdr[1] = message type
    // hdr[2] = payload count (number of float32s)
    // hdr[3] = rolling frame counter

    int count = hdr[2];
    if (count > MAX_COUNT) {
        // Unexpected payload size -- re-sync on next call
        return FrameResult::CRC_ERROR;
    }

    // 3. Read payload
    uint8_t payload[MAX_COUNT * 4];
    int     payloadLen = count * 4;
    if (!readExact(payload, payloadLen)) return FrameResult::IO_ERROR;

    // 4. Read CRC
    uint8_t crcBuf[2];
    if (!readExact(crcBuf, 2)) return FrameResult::IO_ERROR;

    uint16_t receivedCrc = static_cast<uint16_t>(crcBuf[0])
                         | (static_cast<uint16_t>(crcBuf[1]) << 8);

    uint16_t calculatedCrc = crc16Ccitt(hdr, 4, payload, payloadLen);

    if (receivedCrc != calculatedCrc) {
        std::cerr << "CRC mismatch: received 0x" << std::hex << receivedCrc
                  << ", expected 0x" << calculatedCrc << std::dec << "\n";
        return FrameResult::CRC_ERROR;
    }

    // 5. Parse floats (little-endian)
    msgTypeOut = hdr[1];
    countOut   = count;
    for (int i = 0; i < count; ++i) {
        float f;
        std::memcpy(&f, payload + i * 4, 4);
        floatsOut[i] = f;
    }
    return FrameResult::OK;
}

// ---------------------------------------------------------------------------
// High-level helpers
// ---------------------------------------------------------------------------

FrameResult HexFT::readMeasurement(SensorData& out) {
    while (true) {
        uint8_t    msgType;
        float      values[MAX_COUNT];
        int        count = 0;
        FrameResult r = readAnyFrame(msgType, values, count);
        if (r != FrameResult::OK) return r;

        if (msgType == 0x00 && count >= 7) {
            out.fX          = values[0];
            out.fY          = values[1];
            out.fZ          = values[2];
            out.mX          = values[3];
            out.mY          = values[4];
            out.mZ          = values[5];
            out.temperature = values[6];
            return FrameResult::OK;
        }
        // Skip frames of other types and try again
    }
}

FrameResult HexFT::readDiagnostic(SensorDiagnosticData& out) {
    while (true) {
        uint8_t     msgType;
        float       values[MAX_COUNT];
        int         count = 0;
        FrameResult r = readAnyFrame(msgType, values, count);
        if (r != FrameResult::OK) return r;

        if (msgType == 0x02 && count >= 11) {
            out.fX          = values[0];
            out.fY          = values[1];
            out.fZ          = values[2];
            out.mX          = values[3];
            out.mY          = values[4];
            out.mZ          = values[5];
            out.temperature = values[6];
            out.current     = values[7];
            // values[8] is raw ADC voltage -- convert to volts
            float rawV      = values[8];
            float boardV    = values[10];
            out.voltage     = (boardV > 0.0f) ? (rawV / boardV) * 3.3f : 0.0f;
            out.boardTemp   = values[9];
            out.boardVoltage = boardV;
            return FrameResult::OK;
        }
    }
}
