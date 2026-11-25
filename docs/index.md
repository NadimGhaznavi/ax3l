# Ax3l application documentation

Ax3l explores whether a locally hosted language model can improve a Snake AI's
performance by proposing simulation settings and learning from the results.

These documents capture the application's current behavior through four
connected views. They start from actors' goals and explain the responsibilities,
design, and code that realize those goals.

The [shared glossary](glossary.md) defines terminology used across the views.

| View | Purpose | Status |
| --- | --- | --- |
| [Use Case View](use-case/index.md) | Actors, goals, and observable behavior | Initial draft |
| Analysis View | Concepts, responsibilities, and collaborations | To be developed |
| Design View | Software structure, interfaces, and mechanisms | To be developed |
| Implementation View | Source organization and realization of the design | To be developed through refactoring |

We begin with [Deploy Ax3l software](use-case/uc-01-deploy-ax3l-software.md).
Each view is checked against the actual code. We will develop the related
analysis and design, then refactor the implementation while preserving its
observable behavior. Any proposed behavior changes will be identified
explicitly.

This documentation has its own entry point and navigation. The existing public
site remains separate. Markdown links connect the documents, and Mermaid
diagrams illustrate the views.
