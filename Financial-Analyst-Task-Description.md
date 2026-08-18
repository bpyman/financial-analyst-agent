# Financial Analyst Task Description

Hi Blake,

Thanks for confirming the time. I’ve sent out the meeting invite.

For the technical interview, I wanted to share the following problem statement:

## Problem Statement

The goal is to create a financial analyst agent. The agent should be able to perform a wide variety of tasks, similar to an actual financial analyst, such as:

1. Analyze a company's quarterly report, e.g. [Apple's Quarterly Report](https://s2.q4cdn.com/470004039/files/doc_earnings/2025/q3/filing/10Q-Q3-2025-as-filed.pdf), and "reliably" extract key financial details, such as income and costs.

2. For any industry, e.g. finance or healthcare, return a list of the top "N" public companies based on market size.

3. For any industry, e.g. finance or healthcare, explain how AI can cause disruption and the most common use cases that can benefit from AI.

You can think of each of the above tasks as a tool (or API). Depending on the user prompt, the agent will need to figure out which tools it needs to execute. You may design an MCP server to manage the tools, if you choose.

### Example User Prompts

A user prompt can be simple:

> What was Google's net income based on their latest quarterly report?

> What are the top 10 companies in healthcare?

A user prompt can also be complex:

> What are the top 10 companies in healthcare, and what was the reported income for each of those 10 companies?

In this scenario, the agent will have to call more than one tool to accomplish the task.

Please build a solution to accomplish the above.

## Deliverables

1. System design
2. Working POC

## Notes

1. You can use any LLM and any agentic framework (LangChain, Agno, CrewAI, etc.) to develop the POC.
2. If you are making any assumptions in your system design, please explain them.
3. The key is to build a reliable system. Incorrectly extracting values from reports is not ideal.

## Interview Logistics

As discussed, we will run the technical interview on Thursday, 20 August, at 5 p.m. ET.

The interview session will last 1 hour. We will spend the first 25 minutes going over your solution and the remainder of the time on Q&A and brainstorming.

Any questions, feel free to reach out. If not, I will see you on Thursday!

Best,

Rohit
