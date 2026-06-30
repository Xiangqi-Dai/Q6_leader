#include "motor_controller.hpp"
#include <iostream>

using namespace can_infra;

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <mode> <config_file>" << std::endl;
        std::cerr << "Modes: enable, disable, set_zero, send_recv, mit_sine, continuous" << std::endl;
        return 1;
    }

    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    std::string mode = argv[1];
    std::string config_path = argv[2];

    MotorController controller;
    ControlParams params;
    ControlSequence seq;

    if (!load_config(config_path, controller, params, seq)) {
        return 1;
    }

    if (controller.all_motors.empty() && mode != "continuous") {
        std::cerr << "ERR No motors configured" << std::endl;
        return 1;
    }

    if (mode == "enable") {
        controller.enable_all();
        controller.print_states();
    } else if (mode == "disable") {
        controller.disable_all();
        std::cout << "OK" << std::endl;
    } else if (mode == "set_zero") {
        controller.set_zero_all();
        controller.print_states();
    } else if (mode == "send_recv") {
        if (params.has_send_data) {
            uint32_t target = params.has_send_target ? params.send_target : 0;
            controller.send_and_recv(params.send_data, target);
            controller.print_states();
        } else {
            std::cerr << "ERR No send_data in config" << std::endl;
            return 1;
        }
    } else if (mode == "mit_sine") {
        controller.enable_all();
        controller.run_mit_loop(params);
        
        controller.disable_all();
        std::cout << "OK" << std::endl;
    } else if (mode == "continuous") {
        controller.run_continuous(seq);
        std::cout << "OK" << std::endl;
    } else {
        std::cerr << "ERR Unknown mode: " << mode << std::endl;
        return 1;
    }

    return 0;
}
