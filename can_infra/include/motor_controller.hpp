#ifndef MOTOR_CONTROLLER_HPP
#define MOTOR_CONTROLLER_HPP

#include "damiao_motor.hpp"
#include <iostream>
#include <fstream>
#include <sstream>
#include <map>
#include <chrono>
#include <csignal>
#include <sys/timerfd.h>

namespace can_infra {

// Control parameters parsed from config
struct ControlParams {
    float kp = 20.0f;
    float kd = 1.0f;
    float tau_ff = 0.1f;
    float amplitude = 1.0f;
    float sine_freq = 0.1f;
    double duration = 60.0;
    int control_freq = 500;
    int print_freq = 5;
    uint8_t send_data[8] = {0};
    bool has_send_data = false;
    uint32_t send_target = 0;
    bool has_send_target = false;
};

// 命令类型：对应设计文档的接口1~4
enum class CmdType {
    ENABLE,    // 接口1: 电机使能 (0xFC)
    DISABLE,   // 接口2: 电机失能 (0xFD)
    SET_ZERO,  // 接口3: 电机标零 (0xFE)
    CONTROL    // 接口4: CAN信号控制电机 (自定义CAN-data)
};

// 持续控制序列中的单条命令
struct MotorCmdEntry {
    CmdType type;
    uint32_t can_id;       // CAN-ID (slave_id)
    uint8_t can_data[8];   // CAN-data (仅 CONTROL 类型使用)
    uint32_t master_id;    // Master-ID
};

// 持续控制的控制序列
struct ControlSequence {
    int control_frequency = 500;
    int print_frequency = 5;
    double duration = 60.0;
    std::map<std::string, std::vector<MotorCmdEntry>> commands;
};

static volatile bool g_running = true;

inline void signal_handler(int sig) {
    g_running = false;
}

// 发送接口命令帧 (enable/disable/set_zero)
inline void send_cmd_frame(CanBus* bus, uint32_t can_id, uint8_t cmd_byte) {
    uint8_t data[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, cmd_byte};
    bus->send_frame(can_id, data, 8);
}

// Part 2/3: Multi-bus, multi-motor controller
class MotorController {
public:
    std::map<std::string, CanBus*> buses;
    std::vector<DamiaoMotor*> all_motors;
    std::map<uint32_t, DamiaoMotor*> motor_by_slave;
    std::map<std::string, std::vector<DamiaoMotor*>> bus_motors;

    struct BusBuffers {
        std::vector<struct mmsghdr> send_msgs;
        std::vector<struct iovec> send_iovs;
        std::vector<struct canfd_frame> send_frames;
        std::vector<struct mmsghdr> recv_msgs;
        std::vector<struct iovec> recv_iovs;
        std::vector<struct canfd_frame> recv_frames;
    };
    std::map<std::string, BusBuffers> bus_buffers;

    MotorController() = default;

    ~MotorController() {
        for (auto& [name, bus] : buses) delete bus;
        for (auto motor : all_motors) delete motor;
    }

    CanBus* add_bus(const std::string& ifname, bool is_fd) {
        if (buses.count(ifname)) return buses[ifname];
        CanBus* bus = new CanBus(ifname, is_fd);
        auto result = bus->init();
        if (!result.success) {
            std::cerr << result.message << std::endl;
            delete bus;
            return nullptr;
        }
        buses[ifname] = bus;
        bus_motors[ifname] = {};
        return bus;
    }

    DamiaoMotor* add_motor(const std::string& bus_name, uint32_t slave_id,
                           uint32_t master_id, DMMotorType type) {
        auto it = buses.find(bus_name);
        if (it == buses.end()) {
            std::cerr << "[ERROR] Bus not found: " << bus_name << std::endl;
            return nullptr;
        }
        DamiaoMotor* motor = new DamiaoMotor(it->second, slave_id, master_id, type);
        all_motors.push_back(motor);
        motor_by_slave[slave_id] = motor;
        bus_motors[bus_name].push_back(motor);
        return motor;
    }

    void prepare() {
        for (auto& [name, motors] : bus_motors) {
            auto it = buses.find(name);
            if (it == buses.end()) continue;

            size_t n = motors.size();
            auto& buf = bus_buffers[name];
            buf.send_msgs.resize(n);
            buf.send_iovs.resize(n);
            buf.send_frames.resize(n);
            buf.recv_msgs.resize(n * 2);
            buf.recv_iovs.resize(n * 2);
            buf.recv_frames.resize(n * 2);

            for (size_t i = 0; i < n; ++i) {
                buf.send_iovs[i].iov_base = &buf.send_frames[i];
                buf.send_iovs[i].iov_len = sizeof(struct canfd_frame);
                memset(&buf.send_msgs[i], 0, sizeof(struct mmsghdr));
                buf.send_msgs[i].msg_hdr.msg_iov = &buf.send_iovs[i];
                buf.send_msgs[i].msg_hdr.msg_iovlen = 1;
            }
            for (size_t i = 0; i < buf.recv_msgs.size(); ++i) {
                buf.recv_iovs[i].iov_base = &buf.recv_frames[i];
                buf.recv_iovs[i].iov_len = sizeof(struct canfd_frame);
                memset(&buf.recv_msgs[i], 0, sizeof(struct mmsghdr));
                buf.recv_msgs[i].msg_hdr.msg_iov = &buf.recv_iovs[i];
                buf.recv_msgs[i].msg_hdr.msg_iovlen = 1;
            }
        }
    }

    // Print motor states in structured format for Python parsing
    void print_states() {
        std::cout << "OK" << std::endl;
        for (auto motor : all_motors) {
            std::cout << motor->slave_id << " "
                      << motor->state.q << " "
                      << motor->state.dq << " "
                      << motor->state.tau << " "
                      << motor->state.tmos << " "
                      << motor->state.trotor << std::endl;
        }
    }

    void enable_all() {
        for (auto& [name, motors] : bus_motors) {
            for (auto motor : motors) {
                motor->enable();
                usleep(100000);
            }
        }
        usleep(100000);
        recv_all();
    }

    void disable_all() {
        for (auto& [name, motors] : bus_motors) {
            for (auto motor : motors) {
                motor->disable();
                usleep(50000);
            }
        }
    }

    void set_zero_all() {
        for (auto& [name, motors] : bus_motors) {
            for (auto motor : motors) {
                motor->set_zero();
                usleep(100000);
            }
        }
        usleep(100000);
        recv_all();
    }

    void send_and_recv(const uint8_t* data, uint32_t target_id = 0) {
        for (auto motor : all_motors) {
            uint32_t tid = target_id ? target_id : motor->slave_id;
            motor->can_bus->send_frame(tid, data, 8);
        }
        usleep(100000);
        recv_all();
    }

    void send_all() {
        for (auto& [name, motors] : bus_motors) {
            auto buf_it = bus_buffers.find(name);
            if (buf_it == bus_buffers.end()) continue;
            auto& buf = buf_it->second;
            if (motors.empty()) continue;

            for (size_t i = 0; i < motors.size(); ++i) {
                motors[i]->pack_mit_frame(buf.send_frames[i]);
            }
            sendmmsg(buses[name]->sock_fd, buf.send_msgs.data(), motors.size(), 0);
        }
    }

    void recv_all() {
        for (auto& [name, motors] : bus_motors) {
            auto buf_it = bus_buffers.find(name);
            if (buf_it == bus_buffers.end()) continue;
            auto& buf = buf_it->second;
            if (motors.empty()) continue;

            while (true) {
                struct timespec timeout = {0, 0};
                int n = recvmmsg(buses[name]->sock_fd, buf.recv_msgs.data(),
                                 buf.recv_msgs.size(), MSG_DONTWAIT, &timeout);
                if (n <= 0) break;

                for (int i = 0; i < n; ++i) {
                    struct canfd_frame& frame = buf.recv_frames[i];
                    uint32_t id = DamiaoMotor::match_motor_id(frame.can_id, frame.data);

                    auto it = motor_by_slave.find(id);
                    if (it != motor_by_slave.end()) {
                        it->second->parse_feedback(frame.data);
                        continue;
                    }
                    uint32_t id2 = frame.data[0] & 0x0F;
                    if (id2 != 0) {
                        it = motor_by_slave.find(id2);
                        if (it != motor_by_slave.end()) {
                            it->second->parse_feedback(frame.data);
                        }
                    }
                }
            }
        }
    }

    // MIT sine control loop
    void run_mit_loop(const ControlParams& params) {
        int control_freq = params.control_freq;
        int print_freq = params.print_freq;

        int tfd = timerfd_create(CLOCK_MONOTONIC, 0);
        if (tfd == -1) return;

        long long nsec = 1000000000LL / control_freq;
        struct itimerspec its;
        its.it_value.tv_sec = nsec / 1000000000LL;
        its.it_value.tv_nsec = nsec % 1000000000LL;
        its.it_interval.tv_sec = its.it_value.tv_sec;
        its.it_interval.tv_nsec = its.it_value.tv_nsec;

        if (timerfd_settime(tfd, 0, &its, nullptr) == -1) {
            close(tfd);
            return;
        }

        usleep(100000);
        recv_all();
        std::vector<float> init_pos;
        for (auto motor : all_motors) {
            init_pos.push_back(motor->state.q);
        }

        auto start_time = std::chrono::steady_clock::now();
        int loop_count = 0;
        int print_interval = control_freq / print_freq;

        while (g_running) {
            auto now = std::chrono::steady_clock::now();
            std::chrono::duration<double> elapsed = now - start_time;
            if (elapsed.count() > params.duration) break;

            double t = elapsed.count();
            float target = params.amplitude * std::sin(2.0 * M_PI * params.sine_freq * t);

            recv_all();

            if (loop_count % print_interval == 0) {
                std::cout << "[t=" << t << "s]" << std::endl;
                for (auto motor : all_motors) {
                    std::cout << "  Motor " << motor->slave_id
                              << " | Pos: " << motor->state.q
                              << " Vel: " << motor->state.dq
                              << " Tau: " << motor->state.tau << std::endl;
                }
            }

            for (size_t i = 0; i < all_motors.size(); ++i) {
                all_motors[i]->set_mit_cmd(init_pos[i] + target, 0.0f,
                                           params.kp, params.kd, params.tau_ff);
            }
            send_all();

            uint64_t expirations;
            if (read(tfd, &expirations, sizeof(expirations)) != sizeof(expirations)) break;
            loop_count++;
        }

        close(tfd);
    }

    // 特殊接口5: 持续控制 — 通过接口1~4组合实现
    // 序列中包含 ENABLE / SET_ZERO / CONTROL / DISABLE 命令
    // 执行顺序: Phase1(ENABLE) → Phase2(SET_ZERO) → Phase3(CONTROL循环) → Phase4(DISABLE)
    void run_continuous(const ControlSequence& seq) {
        // Phase 1: 执行所有 ENABLE 命令
        std::cout << "[Continuous] Phase 1: Enable" << std::endl;
        for (const auto& [bus_name, cmd_list] : seq.commands) {
            auto bus_it = buses.find(bus_name);
            if (bus_it == buses.end()) continue;
            for (const auto& entry : cmd_list) {
                if (entry.type == CmdType::ENABLE) {
                    send_cmd_frame(bus_it->second, entry.can_id, 0xFC);
                    usleep(100000);
                }
            }
        }
        usleep(200000);
        recv_all();

        // Phase 2: 执行所有 SET_ZERO 命令
        bool has_set_zero = false;
        for (const auto& [bus_name, cmd_list] : seq.commands) {
            for (const auto& entry : cmd_list) {
                if (entry.type == CmdType::SET_ZERO) { has_set_zero = true; break; }
            }
            if (has_set_zero) break;
        }
        if (has_set_zero) {
            std::cout << "[Continuous] Phase 2: Set Zero" << std::endl;
            for (const auto& [bus_name, cmd_list] : seq.commands) {
                auto bus_it = buses.find(bus_name);
                if (bus_it == buses.end()) continue;
                for (const auto& entry : cmd_list) {
                    if (entry.type == CmdType::SET_ZERO) {
                        send_cmd_frame(bus_it->second, entry.can_id, 0xFE);
                        usleep(100000);
                    }
                }
            }
            usleep(200000);
            recv_all();
        }

        // Phase 3: CONTROL 循环
        std::cout << "[Continuous] Phase 3: Control loop at "
                  << seq.control_frequency << " Hz for "
                  << seq.duration << " s" << std::endl;

        int tfd = timerfd_create(CLOCK_MONOTONIC, 0);
        if (tfd == -1) goto phase4;

        {
            long long nsec = 1000000000LL / seq.control_frequency;
            struct itimerspec its;
            its.it_value.tv_sec = nsec / 1000000000LL;
            its.it_value.tv_nsec = nsec % 1000000000LL;
            its.it_interval.tv_sec = its.it_value.tv_sec;
            its.it_interval.tv_nsec = its.it_value.tv_nsec;

            if (timerfd_settime(tfd, 0, &its, nullptr) == -1) {
                close(tfd);
                goto phase4;
            }

            auto start_time = std::chrono::steady_clock::now();
            int loop_count = 0;
            int print_interval = seq.control_frequency / seq.print_frequency;

            while (g_running) {
                auto now = std::chrono::steady_clock::now();
                std::chrono::duration<double> elapsed = now - start_time;
                if (elapsed.count() > seq.duration) break;

                recv_all();

                if (loop_count % print_interval == 0) {
                    double t = elapsed.count();
                    std::cout << "[t=" << t << "s]" << std::endl;
                    for (auto motor : all_motors) {
                        std::cout << "  Motor " << motor->slave_id
                                  << " | Pos: " << motor->state.q
                                  << " Vel: " << motor->state.dq
                                  << " Tau: " << motor->state.tau
                                  << " Tmos: " << motor->state.tmos << std::endl;
                    }
                }

                // 只发送 CONTROL 类型的命令
                for (const auto& [bus_name, cmd_list] : seq.commands) {
                    auto bus_it = buses.find(bus_name);
                    if (bus_it == buses.end()) continue;
                    for (const auto& entry : cmd_list) {
                        if (entry.type == CmdType::CONTROL) {
                            bus_it->second->send_frame(entry.can_id, entry.can_data, 8);
                        }
                    }
                }

                uint64_t expirations;
                if (read(tfd, &expirations, sizeof(expirations)) != sizeof(expirations)) break;
                loop_count++;
            }

            close(tfd);
        }

    phase4:
        // Phase 4: 执行所有 DISABLE 命令
        std::cout << "[Continuous] Phase 4: Disable" << std::endl;
        for (const auto& [bus_name, cmd_list] : seq.commands) {
            auto bus_it = buses.find(bus_name);
            if (bus_it == buses.end()) continue;
            for (const auto& entry : cmd_list) {
                if (entry.type == CmdType::DISABLE) {
                    send_cmd_frame(bus_it->second, entry.can_id, 0xFD);
                    usleep(50000);
                }
            }
        }
        std::cout << "[Continuous] Done" << std::endl;
    }
};

// Load config file
// Format:
//   interface <name> <can|can-fd>
//   motor <id> <type> [<master_id>]
//   kp|kd|tau_ff|amplitude|sine_freq|duration|control_freq|print_freq <value>
//   send_data <8 hex bytes>
//   send_target <hex id>
//   cmd <interface> <enable|disable|set_zero|control> <can_id_hex> [<8 hex bytes>] <master_id_hex>
//     - enable/disable/set_zero: 无CAN-data
//     - control: 有8字节CAN-data
inline bool load_config(const std::string& config_path,
                        MotorController& controller,
                        ControlParams& params,
                        ControlSequence& seq) {
    std::ifstream infile(config_path);
    if (!infile.is_open()) {
        std::cerr << "ERR Cannot open config: " << config_path << std::endl;
        return false;
    }

    std::string line;
    std::string current_bus;

    while (std::getline(infile, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::stringstream ss(line);
        std::string token;
        ss >> token;

        if (token == "interface") {
            std::string type_str;
            ss >> current_bus >> type_str;
            bool is_fd = (type_str == "can-fd");
            if (!controller.add_bus(current_bus, is_fd)) return false;
        } else if (token == "motor") {
            int id;
            std::string type_str;
            ss >> id >> type_str;
            int master_id_val = id + 0x10;
            ss >> master_id_val;
            DMMotorType type;
            if (!string_to_motor_type(type_str, type)) {
                type = DMMotorType::DM4310;
            }
            controller.add_motor(current_bus, static_cast<uint32_t>(id),
                                 static_cast<uint32_t>(master_id_val), type);
        } else if (token == "kp")           { ss >> params.kp; }
        else if (token == "kd")             { ss >> params.kd; }
        else if (token == "tau_ff")         { ss >> params.tau_ff; }
        else if (token == "amplitude")      { ss >> params.amplitude; }
        else if (token == "sine_freq")      { ss >> params.sine_freq; }
        else if (token == "duration")       { ss >> params.duration; }
        else if (token == "control_freq")   { ss >> params.control_freq; }
        else if (token == "print_freq")     { ss >> params.print_freq; }
        else if (token == "send_target")    { ss >> params.send_target; params.has_send_target = true; }
        else if (token == "send_data") {
            for (int i = 0; i < 8; ++i) {
                int b; ss >> std::hex >> b; params.send_data[i] = b & 0xFF;
            }
            params.has_send_data = true;
        } else if (token == "seq_control_freq") { ss >> seq.control_frequency; }
        else if (token == "seq_print_freq")     { ss >> seq.print_frequency; }
        else if (token == "seq_duration")       { ss >> seq.duration; }
        else if (token == "cmd") {
            std::string iface, type_str;
            int can_id_val, mid;
            ss >> iface >> type_str >> std::hex >> can_id_val;

            MotorCmdEntry entry;
            entry.can_id = can_id_val;
            memset(entry.can_data, 0, 8);

            if (type_str == "enable") {
                entry.type = CmdType::ENABLE;
            } else if (type_str == "disable") {
                entry.type = CmdType::DISABLE;
            } else if (type_str == "set_zero") {
                entry.type = CmdType::SET_ZERO;
            } else {
                // control: 需要读取 8 字节 CAN-data
                entry.type = CmdType::CONTROL;
                for (int i = 0; i < 8; ++i) {
                    int b; ss >> std::hex >> b; entry.can_data[i] = b & 0xFF;
                }
            }
            ss >> std::hex >> mid;
            entry.master_id = mid;
            seq.commands[iface].push_back(entry);
        }
    }

    controller.prepare();
    return true;
}

} // namespace can_infra

#endif // MOTOR_CONTROLLER_HPP
