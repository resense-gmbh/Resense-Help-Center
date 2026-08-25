// main_protocol.cpp -- Example program using the protocol (framed + CRC) mode.
// See HexFT_Protocol.h for full protocol documentation.
//
// Build:
//   g++ -std=c++11 -o read_sensor main_protocol.cpp HexFT_Protocol.cpp
//
// Run:
//   ./read_sensor

#include <csignal>
#include <iomanip>
#include <iostream>
#include "HexFT_Protocol.h"

static volatile bool running = true;

static void onSigInt(int) {
    running = false;
}

int main() {
    // Adjust the port name to match your setup:
    //   Linux:   "/dev/ttyACM0"  or  "/dev/ttyUSB0"
    //   macOS:   "/dev/tty.usbmodem1234"  (check 'ls /dev/tty.*')
    HexFT sensor("COM143");

    if (!sensor.isOpen()) {
        std::cerr << "Failed to open serial port. "
                     "Check the port name and permissions.\n";
        return 1;
    }

    std::signal(SIGINT, onSigInt);
    std::cout << "Reading sensor data in protocol mode. Press Ctrl+C to stop.\n";
    std::cout << "(Switch measurement/diagnostic mode in Force/Torque Explorer settings)\n\n";

    std::cout << std::fixed << std::setprecision(3);

    while (running) {
        // ---------------------------------------------------------------
        // Option A: Read only basic measurement frames (type 0x00)
        // ---------------------------------------------------------------
        SensorData d;
        FrameResult r = sensor.readMeasurement(d);
        if (r == FrameResult::IO_ERROR) {
            std::cerr << "I/O error -- sensor disconnected?\n";
            break;
        }
        if (r == FrameResult::CRC_ERROR) {
            std::cerr << "CRC error -- retrying...\n";
            continue;
        }

        std::cout
            << "[MEAS]  "
            << "Fx="   << std::setw(10) << d.fX
            << "  Fy=" << std::setw(10) << d.fY
            << "  Fz=" << std::setw(10) << d.fZ
            << "  Mx=" << std::setw(10) << d.mX
            << "  My=" << std::setw(10) << d.mY
            << "  Mz=" << std::setw(10) << d.mZ
            << "  Temp=" << std::setw(7) << d.temperature << " C\n";

        // ---------------------------------------------------------------
        // Option B: Read extended diagnostic frames (type 0x02)
        //           Uncomment the block below and comment out Option A.
        // ---------------------------------------------------------------
        /*
        SensorDiagnosticData diag;
        FrameResult r = sensor.readDiagnostic(diag);
        if (r == FrameResult::IO_ERROR) {
            std::cerr << "I/O error -- sensor disconnected?\n";
            break;
        }
        if (r == FrameResult::CRC_ERROR) {
            std::cerr << "CRC error -- retrying...\n";
            continue;
        }

        std::cout
            << "[DIAG]  "
            << "Fx="         << std::setw(10) << diag.fX
            << "  Fy="       << std::setw(10) << diag.fY
            << "  Fz="       << std::setw(10) << diag.fZ
            << "  Mx="       << std::setw(10) << diag.mX
            << "  My="       << std::setw(10) << diag.mY
            << "  Mz="       << std::setw(10) << diag.mZ
            << "  Temp="     << std::setw(7)  << diag.temperature  << " C"
            << "  I="        << std::setw(7)  << diag.current      << " A"
            << "  V="        << std::setw(7)  << diag.voltage      << " V"
            << "  BrdTemp="  << std::setw(7)  << diag.boardTemp    << " C"
            << "  BrdV="     << std::setw(7)  << diag.boardVoltage << " V\n";
        */
    }

    std::cout << "\nStopped.\n";
    return 0;
}
