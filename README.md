# CodeAgent

An autonomous AI coding agent that transforms software architecture documentation and UML diagrams into structured software projects using the official DeepSeek V4 Pro API.

## Overview

CodeAgent is a Windows desktop application designed to automate software project generation from architecture documentation.

Users can provide architecture documents, UML diagrams, configure their DeepSeek API key, and specify an output directory. The agent analyzes the supplied materials and generates project files through an iterative AI tool-calling workflow.

## Key Features

- DeepSeek V4 Pro API integration.
- Autonomous AI agent workflow.
- Architecture documentation preprocessing.
- PlantUML diagram processing.
- Automated project file generation.
- Tool-based file operations.
- Windows desktop graphical interface.
- API usage tracking.
- Project validation and automated tests.
- Standalone Windows executable packaging.

## Target Project: Space Fractions

The project demonstrates architecture-driven software generation using Space Fractions, an educational mathematics game designed for sixth-grade students.

The generated game is intended to provide an interactive desktop learning experience with fraction questions, answer feedback, scoring, and a final results screen.

## Technology Stack

- Python
- Tkinter
- DeepSeek V4 Pro API
- REST API / Tool Calling
- PlantUML
- PyInstaller
- Pytest

## Project Structure

The repository contains the CodeAgent source code, tests, documentation, configuration files, and Windows build instructions.

## Getting Started

1. Clone the repository.
2. Install the dependencies listed in requirements.txt.
3. Configure your DeepSeek API key.
4. Launch the application.
5. Select the architecture documentation and UML diagram files.
6. Choose an output directory.
7. Start the agent and review the generated project.

## Windows Executable

A standalone Windows executable is provided through the GitHub Releases section.

## Testing

The project includes automated tests for core functionality, agent operations, and supporting components. Refer to the test documentation for execution instructions and results.

## Research References

- https://github.com/ultraworkers/claw-code
- https://github.com/Windy3f3f3f3f/how-claude-code-works
- https://github.com/anthropics/claude-code

## Disclaimer

This project is an educational implementation of a simplified AI coding agent. DeepSeek API access requires a valid API key.
