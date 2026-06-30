#ifndef DAMIAO_MOTOR_HPP
#define DAMIAO_MOTOR_HPP

#include "can_bus.hpp"
#include <cmath>
#include <cstring>

namespace can_infra {

// Motor types
enum class DMMotorType {
    DM4310 = 0,
    DM4310_48V = 1,
    DM4340 = 2,
    DM4340_48V = 3,
    DM6006 = 4,
    DM8006 = 5,
    DM8009 = 6,
    DM10010L = 7,
    DM10010 = 8,
    DMH3510 = 9,
    DMG62150 = 10,
    DMH6220 = 11,
    DM4340P_48V = 12
};

inline const char* motor_type_to_string(DMMotorType type) {
    switch (type) {
        case DMMotorType::DM4310:     return "DM4310";
        case DMMotorType::DM4310_48V: return "DM4310_48V";
        case DMMotorType::DM4340:     return "DM4340";
        case DMMotorType::DM4340_48V: return "DM4340_48V";
        case DMMotorType::DM6006:     return "DM6006";
        case DMMotorType::DM8006:     return "DM8006";
        case DMMotorType::DM8009:     return "DM8009";
        case DMMotorType::DM10010L:   return "DM10010L";
        case DMMotorType::DM10010:    return "DM10010";
        case DMMotorType::DMH3510:    return "DMH3510";
        case DMMotorType::DMG62150:   return "DMG62150";
        case DMMotorType::DMH6220:    return "DMH6220";
        case DMMotorType::DM4340P_48V:return "DM4340P_48V";
        default: return "UNKNOWN";
    }
}

inline bool string_to_motor_type(const std::string& s, DMMotorType& type) {
    if (s == "DM4310")          { type = DMMotorType::DM4310; return true; }
    if (s == "DM4310_48V")      { type = DMMotorType::DM4310_48V; return true; }
    if (s == "DM4340")          { type = DMMotorType::DM4340; return true; }
    if (s == "DM4340_48V")      { type = DMMotorType::DM4340_48V; return true; }
    if (s == "DM6006")          { type = DMMotorType::DM6006; return true; }
    if (s == "DM8006")          { type = DMMotorType::DM8006; return true; }
    if (s == "DM8009")          { type = DMMotorType::DM8009; return true; }
    if (s == "DM10010L")        { type = DMMotorType::DM10010L; return true; }
    if (s == "DM10010")         { type = DMMotorType::DM10010; return true; }
    if (s == "DMH3510")         { type = DMMotorType::DMH3510; return true; }
    if (s == "DMG62150")        { type = DMMotorType::DMG62150; return true; }
    if (s == "DMH6220")         { type = DMMotorType::DMH6220; return true; }
    if (s == "DM4340P_48V")     { type = DMMotorType::DM4340P_48V; return true; }
    return false;
}

// Limit parameters per motor type: [PMAX, VMAX, TMAX]
struct LimitParam {
    float PMAX;
    float VMAX;
    float TMAX;
};

inline LimitParam get_limit_param(DMMotorType type) {
    switch (type) {
        case DMMotorType::DM4310:      return {12.5f, 30.0f, 10.0f};
        case DMMotorType::DM4310_48V:  return {12.5f, 50.0f, 10.0f};
        case DMMotorType::DM4340:      return {12.5f, 8.0f,  28.0f};
        case DMMotorType::DM4340_48V:  return {12.5f, 10.0f, 28.0f};
        case DMMotorType::DM6006:      return {12.5f, 45.0f, 20.0f};
        case DMMotorType::DM8006:      return {12.5f, 45.0f, 40.0f};
        case DMMotorType::DM8009:      return {12.5f, 45.0f, 54.0f};
        case DMMotorType::DM10010L:    return {12.5f, 25.0f, 200.0f};
        case DMMotorType::DM10010:     return {12.5f, 20.0f, 200.0f};
        case DMMotorType::DMH3510:     return {12.5f, 280.0f, 1.0f};
        case DMMotorType::DMG62150:    return {12.5f, 45.0f, 10.0f};
        case DMMotorType::DMH6220:     return {12.5f, 45.0f, 10.0f};
        case DMMotorType::DM4340P_48V: return {12.5f, 8.0f,  28.0f};
        default:                        return {12.5f, 30.0f, 10.0f};
    }
}

// Utility: float <-> uint conversion for Damiao protocol
inline uint16_t float_to_uint(float x, float x_min, float x_max, int bits) {
    x = std::max(x_min, std::min(x, x_max));
    float span = x_max - x_min;
    float data_norm = (x - x_min) / span;
    return static_cast<uint16_t>(data_norm * ((1 << bits) - 1));
}

inline float uint_to_float(uint16_t x, float x_min, float x_max, int bits) {
    float span = x_max - x_min;
    float data_norm = static_cast<float>(x) / ((1 << bits) - 1);
    return data_norm * span + x_min;
}

// Motor feedback state
struct MotorState {
    float q = 0.0f;      // position (rad)
    float dq = 0.0f;     // velocity (rad/s)
    float tau = 0.0f;    // torque (Nm)
    int tmos = 0;        // MOS temperature
    int trotor = 0;      // rotor temperature
};

// Motor command
struct MotorCmd {
    float q = 0.0f;      // target position
    float dq = 0.0f;     // target velocity
    float kp = 0.0f;     // position gain
    float kd = 0.0f;     // velocity gain
    float tau = 0.0f;    // feedforward torque
};

// Part 2: Damiao Motor
// Motor struct: CAN_interface, CAN_ID(slave_id), Master_ID(master_id)
class DamiaoMotor {
public:
    CanBus* can_bus;
    uint32_t slave_id;     // CAN-ID (电机的CAN-ID)
    uint32_t master_id;    // Master-ID (电机的主机ID)
    DMMotorType type;
    bool is_fd;
    MotorState state;
    MotorCmd cmd;
    LimitParam limits;

    DamiaoMotor(CanBus* bus, uint32_t sid, uint32_t mid, DMMotorType t)
        : can_bus(bus), slave_id(sid), master_id(mid), type(t),
          is_fd(bus ? bus->is_fd : true), limits(get_limit_param(t)) {}

    // Part 2: CAN信号控制电机
    // Send CAN-data to CAN-ID, then receive from Master-ID
    bool control(const uint8_t* can_data, uint8_t len) {
        if (!can_bus || can_bus->sock_fd < 0) return false;
        if (!can_bus->send_frame(slave_id, can_data, len)) return false;
        return recv_feedback();
    }

    // Part 2: 特殊接口1 - 电机使能 (enable)
    bool enable() {
        uint8_t data[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFC};
        return can_bus && can_bus->send_frame(slave_id, data, 8);
    }

    // Part 2: 特殊接口2 - 电机失能 (disable)
    bool disable() {
        uint8_t data[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFD};
        return can_bus && can_bus->send_frame(slave_id, data, 8);
    }

    // Part 2: 特殊接口3 - 电机标零 (set zero position)
    bool set_zero() {
        uint8_t data[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFE};
        return can_bus && can_bus->send_frame(slave_id, data, 8);
    }

    // Set MIT command parameters
    void set_mit_cmd(float q_des, float dq_des, float kp, float kd, float tau_ff) {
        cmd.q = q_des;
        cmd.dq = dq_des;
        cmd.kp = kp;
        cmd.kd = kd;
        cmd.tau = tau_ff;
    }

    // Pack MIT control into a CAN frame buffer
    void pack_mit_ctrl(uint8_t* out_data) const {
        uint16_t q_uint = float_to_uint(cmd.q, -limits.PMAX, limits.PMAX, 16);
        uint16_t dq_uint = float_to_uint(cmd.dq, -limits.VMAX, limits.VMAX, 12);
        uint16_t kp_uint = float_to_uint(cmd.kp, 0.0f, 500.0f, 12);
        uint16_t kd_uint = float_to_uint(cmd.kd, 0.0f, 5.0f, 12);
        uint16_t tau_uint = float_to_uint(cmd.tau, -limits.TMAX, limits.TMAX, 12);

        out_data[0] = (q_uint >> 8) & 0xFF;
        out_data[1] = q_uint & 0xFF;
        out_data[2] = dq_uint >> 4;
        out_data[3] = ((dq_uint & 0xF) << 4) | ((kp_uint >> 8) & 0xF);
        out_data[4] = kp_uint & 0xFF;
        out_data[5] = kd_uint >> 4;
        out_data[6] = ((kd_uint & 0xF) << 4) | ((tau_uint >> 8) & 0xF);
        out_data[7] = tau_uint & 0xFF;
    }

    // Pack MIT control into canfd_frame (for batch send)
    void pack_mit_frame(struct canfd_frame& frame) const {
        frame.can_id = slave_id;
        frame.len = 8;
        frame.flags = is_fd ? (CANFD_FDF | CANFD_BRS) : 0;
        pack_mit_ctrl(frame.data);
    }

    // Pack command byte frame (enable/disable/set_zero)
    void pack_cmd_frame(struct canfd_frame& frame, uint8_t cmd_byte) const {
        frame.can_id = slave_id;
        frame.len = 8;
        frame.flags = is_fd ? (CANFD_FDF | CANFD_BRS) : 0;
        for (int i = 0; i < 7; ++i) frame.data[i] = 0xFF;
        frame.data[7] = cmd_byte;
    }

    // Parse feedback data from CAN frame
    void parse_feedback(const uint8_t* data) {
        uint16_t q_uint = (static_cast<uint16_t>(data[1]) << 8) | data[2];
        uint16_t dq_uint = (static_cast<uint16_t>(data[3]) << 4) | (data[4] >> 4);
        uint16_t tau_uint = ((data[4] & 0xF) << 8) | data[5];

        state.q = uint_to_float(q_uint, -limits.PMAX, limits.PMAX, 16);
        state.dq = uint_to_float(dq_uint, -limits.VMAX, limits.VMAX, 12);
        state.tau = uint_to_float(tau_uint, -limits.TMAX, limits.TMAX, 12);
        state.tmos = data[6];
        state.trotor = data[7];
    }

    // Receive feedback from CAN bus (tries to match by slave_id or master_id)
    bool recv_feedback() {
        if (!can_bus || can_bus->sock_fd < 0) return false;

        uint32_t can_id;
        uint8_t data[64];
        uint8_t len;

        // Try to receive a few frames looking for our response
        for (int attempt = 0; attempt < 10; ++attempt) {
            if (can_bus->recv_frame(can_id, data, len)) {
                // Try to match by arbitration ID or data[0]
                uint32_t match_id = match_motor_id(can_id, data);
                if (match_id == slave_id || match_id == master_id) {
                    parse_feedback(data);
                    return true;
                }
            } else {
                break;
            }
        }
        return false;
    }

    // Match a received CAN frame to this motor's ID
    static uint32_t match_motor_id(uint32_t arb_id, const uint8_t* data) {
        // Follow Damiao protocol: check arb_id and data[0] for motor identification
        if (data[0] != 0xFF && data[0] != 0x00 && ((data[0] & 0x0F) != 0)) {
            uint32_t id = data[0] & 0x0F;
            if (id != 0) return id;
        }
        return arb_id & 0xFF;
    }

    // Getters for motor state
    float get_position() const { return state.q; }
    float get_velocity() const { return state.dq; }
    float get_torque() const { return state.tau; }
};

} // namespace can_infra

#endif // DAMIAO_MOTOR_HPP
