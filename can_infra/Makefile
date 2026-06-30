CXX = g++
CXXFLAGS = -std=c++20 -O3 -Wall -Iinclude

TARGET = main
SRCS = src/main.cpp

all: $(TARGET)

$(TARGET): $(SRCS) include/can_bus.hpp include/damiao_motor.hpp include/motor_controller.hpp
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(SRCS)

clean:
	rm -f $(TARGET)

.PHONY: all clean
