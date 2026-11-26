# Ax3l application documentation

Ax3l explores whether a locally hosted language model can improve a Snake AI's
performance by proposing simulation settings and learning from the results.

These documents capture the application's current behavior through four
connected views. They start from actors' goals and explain the responsibilities,
design, and code that realize those goals.

The [shared glossary](glossary.md) defines terminology used across the views.
The [application structure](implementation/architecture.md) maps the code's
current responsibilities and verification commands.

| View | Purpose | Status |
| --- | --- | --- |
| [Use Case View](use-case/index.md) | Actors, goals, and observable behavior | Initial draft |
| [Analysis View](analysis/index.md) | Concepts, responsibilities, and collaborations | Initial draft |
| [Design View](design/index.md) | Software structure, interfaces, and mechanisms | Initial draft |
| [Implementation View](implementation/index.md) | Source organization and realization of the design | Initial implementation |

We begin with [Deploy Ax3l software](use-case/uc-01-deploy-ax3l-software.md).
The use case can be followed through all four views. Each view is checked against
the actual code, and focused refactoring keeps the implementation aligned with
the documented contracts. Any proposed behavior changes are identified explicitly.

This documentation has its own entry point and navigation. The existing public
site remains separate. Markdown links connect the documents, and Mermaid
diagrams illustrate the views.
