# spec-compiler
Generates gamemaker code from specs

## Goals

This project was designed to let game designers write specs for dialogue games, and convert the specs to functional gamemaker code. In addition, it was designed to be simple enough to allow new programmers to maintain it.

There are several cases the code must handle:

* The player thinking
* Dialogue between characters
* Conditional checks to allow an option, or not
* Long branches based on choices

## Design
The core abstraction is the "Parseable" class, a recursive type that is generated from a block of text and can be turned into some number of gamemaker cases.

In particular, the if-else and branch parseables can take other parseables as inputs (including other if-else or branch parseables), which allows for arbitrary nesting.
