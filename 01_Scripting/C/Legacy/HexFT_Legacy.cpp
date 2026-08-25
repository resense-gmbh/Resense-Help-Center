// HexFT_Legacy.cpp -- Implementation for legacy (raw binary) mode.
// See HexFT_Legacy.h for documentation.

#include "HexFT_Legacy.h"

#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <termios.h>
#include <unistd.h>

HexFT::HexFT(const std::string& serialPort) {
    _fd = open(serialPort.c_str(), O_RDWR | O_NOCTTY);
    if (_fd < 0) {
        std::cerr << "Error opening " << serialPort << ": "
                  << strerror(errno) << "\n";
        return;
    }

    // Configure POSIX serial port: 1 Mbit/s, 8-N-1, raw (non-canonical) mode
    struct termios tty{};
    if (tcgetattr(_fd, &tty) != 0) {
        std::cerr << "tcgetattr failed: " << strerror(errno) << "\n";
        close(_fd);
        _fd = -1;
        return;
    }

    cfsetispeed(&tty, B1000000);  // 1 Mbit/s input
    cfsetospeed(&tty, B1000000);  // 1 Mbit/s output
    cfmakeraw(&tty);              // raw mode: no line discipline processing

    tty.c_cc[VMIN]  = 1;  // block until at least 1 byte is available
    tty.c_cc[VTIME] = 10; // inter-character timeout: 1 second

    if (tcsetattr(_fd, TCSANOW, &tty) != 0) {
        std::cerr << "tcsetattr failed: " << strerror(errno) << "\n";
        close(_fd);
        _fd = -1;
    }
}

HexFT::~HexFT() {
    if (_fd >= 0)
        close(_fd);
}

SensorData HexFT::readSensorData() {
    SensorData data{};
    auto*      dst       = reinterpret_cast<uint8_t*>(&data);
    int        remaining = static_cast<int>(sizeof(data)); // 28 bytes

    while (remaining > 0) {
        int n = read(_fd, dst, remaining);
        if (n <= 0)
            break; // timeout or I/O error -- return whatever was read so far
        dst       += n;
        remaining -= n;
    }
    return data;
}
