# CodeAgent 3.1.0 – User Guide

CodeAgent is an AI-powered coding agent that transforms software architecture documentation and architecture diagrams into structured software projects.

## 🚀 How to Use CodeAgent

### Step 1. Launch the Application
Download and launch the CodeAgent Windows executable from the GitHub Releases section.

### Step 2. Configure the AI Provider
- Select your preferred AI provider.
- Choose an available AI model.
- Configure the required settings, such as region or Workspace ID.
- Enable thinking if supported by the selected model.

### Step 3. Configure Your API Key
- Obtain an API key from your selected provider.
- Paste it into the **API Key** field.
- Click **Test Connection** to verify the connection.
- Click **Save Key** to save your configuration.

### Step 4. Provide Architecture Files

Under the **Task Inputs & Output** section, provide:

- **Architecture Documentation (.md):** Select your software architecture documentation.
- **Architecture Views (.md):** Select your architecture diagrams and views.
- **Output Directory:** Choose where the generated project will be saved.

### Step 5. Add Extra Instructions (Optional)
Provide additional requirements, such as the programming language, interface design, or testing requirements.

### Step 6. Start CodeAgent
Click **Start** to begin the generation process. The agent will analyze the provided architecture materials and generate the software project.

### Step 7. Monitor Execution
Use the available controls to manage the workflow:

- **Stop:** Stop execution.
- **Resume:** Continue execution when supported.
- **Restart:** Restart the workflow.
- **Status:** Check the current execution status.
- **Open Output:** Open the generated project directory.

You can also monitor the agent's activities through the **Agent Activity Log**.

### Step 8. Review the Generated Project
Once generation is complete:

1. Open the output directory.
2. Review the generated source code and project structure.
3. Run the generated application.
4. Verify its functionality and execute the available tests.

## 💰 Token Usage & Cost

CodeAgent provides usage information, including:

- Input and output tokens.
- Number of API requests.
- Estimated API cost.
- Remaining budget.

## 🎮 Example Project: Space Fractions

CodeAgent can be used to generate **Space Fractions**, an educational mathematics game for sixth-grade students featuring interactive fraction questions, answer feedback, scoring, and a final results screen.

## ⚠️ Important Notes

- A valid API key is required.
- API usage may incur charges depending on the provider and model.
- Keep your API key private.
- Always review generated code before running it.
