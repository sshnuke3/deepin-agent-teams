.PHONY: build run demo test clean build-all tidy

BINARY=bin/deepin-agent
VERSION=$(shell git describe --tags --always --dirty 2>/dev/null || echo "v0.0.0")
LDFLAGS=-ldflags "-X main.version=$(VERSION)"

# 默认目标
all: build

# 编译
build:
	go build $(LDFLAGS) -o $(BINARY) ./cmd/deepin-agent

# 跑 chat 模式（需要 AGNES_API_KEY）
run: build
	./$(BINARY) chat "$(MSG)"

# 跑内置 demo
demo: build
	./$(BINARY) --demo

# 单元测试
test:
	go test ./...

# 清理
clean:
	rm -rf bin/

# 跨平台编译
build-all:
	GOOS=linux GOARCH=amd64 go build $(LDFLAGS) -o bin/deepin-agent-linux-amd64 ./cmd/deepin-agent
	GOOS=linux GOARCH=arm64 go build $(LDFLAGS) -o bin/deepin-agent-linux-arm64 ./cmd/deepin-agent
	GOOS=darwin GOARCH=arm64 go build $(LDFLAGS) -o bin/deepin-agent-darwin-arm64 ./cmd/deepin-agent

# 依赖同步
tidy:
	go mod tidy
