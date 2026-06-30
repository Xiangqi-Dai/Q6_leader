#ifndef CAN_BUS_HPP
#define CAN_BUS_HPP

#include <cstdint>
#include <string>
#include <vector>
#include <cstring>
#include <unistd.h>
#include <fcntl.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <linux/can.h>
#include <linux/can/raw.h>

namespace can_infra {

// CAN bus initialization result
struct CanInitResult {
    bool success = false;
    std::string message;
};

// Part 1: CAN bus communication layer
// Provides raw CAN frame send/receive on a single CAN interface
class CanBus {
public:
    std::string ifname;
    bool is_fd;
    int sock_fd;

    CanBus(const std::string& name, bool fd = true)
        : ifname(name), is_fd(fd), sock_fd(-1) {}

    ~CanBus() {
        if (sock_fd >= 0) {
            close(sock_fd);
        }
    }

    // Part 1: CAN init
    // input: CAN口名称, 是否CAN-FD (构造函数), arbitration bitrate, data bitrate
    // note: bitrate由外部(ip link命令)或config_manager配置，此处只初始化socket
    CanInitResult init() {
        CanInitResult result;

        sock_fd = socket(PF_CAN, SOCK_RAW, CAN_RAW);
        if (sock_fd < 0) {
            result.success = false;
            result.message = "socket PF_CAN failed: " + std::string(strerror(errno));
            return result;
        }

        int enable_canfd = 1;
        if (setsockopt(sock_fd, SOL_CAN_RAW, CAN_RAW_FD_FRAMES,
                       &enable_canfd, sizeof(enable_canfd)) < 0) {
            result.message = "setsockopt CAN_RAW_FD_FRAMES failed (non-fatal)";
        }

        struct ifreq ifr;
        memset(&ifr, 0, sizeof(ifr));
        strncpy(ifr.ifr_name, ifname.c_str(), IFNAMSIZ - 1);
        if (ioctl(sock_fd, SIOCGIFINDEX, &ifr) < 0) {
            result.success = false;
            result.message = "ioctl SIOCGIFINDEX failed for " + ifname + ": " + strerror(errno);
            close(sock_fd);
            sock_fd = -1;
            return result;
        }

        struct sockaddr_can addr;
        memset(&addr, 0, sizeof(addr));
        addr.can_family = AF_CAN;
        addr.can_ifindex = ifr.ifr_ifindex;

        if (bind(sock_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            result.success = false;
            result.message = "bind failed for " + ifname + ": " + strerror(errno);
            close(sock_fd);
            sock_fd = -1;
            return result;
        }

        // Set non-blocking for recv
        int flags = fcntl(sock_fd, F_GETFL, 0);
        fcntl(sock_fd, F_SETFL, flags | O_NONBLOCK);

        result.success = true;
        result.message = "CAN interface " + ifname + " initialized successfully";
        return result;
    }

    // Part 1: 发CAN frame
    // input: CAN-ID, CAN-data, len
    bool send_frame(uint32_t can_id, const uint8_t* data, uint8_t len) {
        struct canfd_frame frame;
        memset(&frame, 0, sizeof(frame));
        frame.can_id = can_id;
        frame.len = len;
        frame.flags = is_fd ? (CANFD_FDF | CANFD_BRS) : 0;
        memcpy(frame.data, data, len);

        ssize_t nbytes = write(sock_fd, &frame, sizeof(frame));
        return nbytes == sizeof(frame);
    }

    // Part 1: 收CAN frame
    // input: timeout_ms (-1 for non-blocking)
    // output: can_id, data, len
    bool recv_frame(uint32_t& can_id, uint8_t* data, uint8_t& len, int timeout_ms = 0) {
        struct canfd_frame frame;
        ssize_t nbytes = read(sock_fd, &frame, sizeof(frame));
        if (nbytes < 0) {
            return false; // EAGAIN or error
        }
        can_id = frame.can_id;
        len = frame.len;
        memcpy(data, frame.data, frame.len);
        return true;
    }

    // Batch send using sendmmsg for efficiency
    int send_batch(const std::vector<struct canfd_frame>& frames) {
        if (frames.empty()) return 0;

        size_t n = frames.size();
        std::vector<struct mmsghdr> msgs(n);
        std::vector<struct iovec> iovs(n);

        for (size_t i = 0; i < n; ++i) {
            iovs[i].iov_base = const_cast<struct canfd_frame*>(&frames[i]);
            iovs[i].iov_len = sizeof(struct canfd_frame);
            memset(&msgs[i], 0, sizeof(struct mmsghdr));
            msgs[i].msg_hdr.msg_iov = &iovs[i];
            msgs[i].msg_hdr.msg_iovlen = 1;
        }

        return sendmmsg(sock_fd, msgs.data(), n, 0);
    }

    // Batch recv using recvmmsg for efficiency
    int recv_batch(std::vector<struct canfd_frame>& out_frames, size_t max_count) {
        out_frames.resize(max_count);
        std::vector<struct mmsghdr> msgs(max_count);
        std::vector<struct iovec> iovs(max_count);

        for (size_t i = 0; i < max_count; ++i) {
            iovs[i].iov_base = &out_frames[i];
            iovs[i].iov_len = sizeof(struct canfd_frame);
            memset(&msgs[i], 0, sizeof(struct mmsghdr));
            msgs[i].msg_hdr.msg_iov = &iovs[i];
            msgs[i].msg_hdr.msg_iovlen = 1;
        }

        struct timespec timeout = {0, 0};
        int n = recvmmsg(sock_fd, msgs.data(), max_count, MSG_DONTWAIT, &timeout);
        if (n > 0) {
            out_frames.resize(n);
        } else {
            out_frames.clear();
        }
        return n;
    }
};

} // namespace can_infra

#endif // CAN_BUS_HPP
