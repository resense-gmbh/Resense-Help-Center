// main_legacy.cpp -- Example program using the legacy (raw binary) mode.
// See HexFT_Legacy.h for protocol details.
//
// Build:
//   g++ -std=c++11 -o read_sensor main_legacy.cpp HexFT_Legacy.cpp
//
// Run:
//   ./read_sensor

#include <csignal>
#include <iomanip>
#include <iostream>
#include "HexFT_Legacy.h"

static volatile bool running = true;

static void onSigInt(int) {
    running = false;
}

int main() {
    // Adjust the port name to match your setup:
    //   Linux:   "/dev/ttyACM0"  or  "/dev/ttyUSB0"
    //   macOS:   "/dev/tty.usbmodem1234"  (check 'ls /dev/tty.*')
    HexFT sensor("/dev/ttyACM0");

    if (!sensor.isOpen()) {
        std::cerr << "Failed to open serial port. "
                     "Check the port name and permissions.\n";
        return 1;
    }

    std::signal(SIGINT, onSigInt);
    std::cout << "Reading sensor data in legacy mode. Press Ctrl+C to stop.\n\n";

    std::cout << std::fixed << std::setprecision(3);

    while (running) {
        SensorData d = sensor.readSensorData();

        std::cout
            << "Fx=" << std::setw(10) << d.fX
            << "  Fy=" << std::setw(10) << d.fY
            << "  Fz=" << std::setw(10) << d.fZ
            << "  Mx=" << std::setw(10) << d.mX
            << "  My=" << std::setw(10) << d.mY
            << "  Mz=" << std::setw(10) << d.mZ
            << "  Temp=" << std::setw(7) << d.temperature << " C\n";
    }

    std::cout << "\nStopped.\n";
    return 0;
}
