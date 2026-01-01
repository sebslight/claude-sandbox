# Claude Code Sandbox
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install base dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    ripgrep \
    jq \
    fzf \
    zsh \
    sudo \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install Python 3.13 via uv
RUN uv python install 3.13

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code@latest

# Create non-root user
RUN useradd -m -s /bin/zsh claude \
    && echo "claude ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Set up uv for claude user
USER claude
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/claude/.local/bin:$PATH"

# Create .claude directory
RUN mkdir -p /home/claude/.claude

WORKDIR /workspace
