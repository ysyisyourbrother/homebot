

<p align="center">
  <img src="images/logo_2.png" alt="Homebot" width="560">
</p>

<p align="center">
  📄 Technical Report: <a href="https://arxiv.org/pdf/2608.02254">Homebot: A Personal AI Agent for Conversational Home Assistance and Automation</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-%E2%89%A53.11-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <a href="https://ysyisyourbrother.github.io/homebot/"><img src="https://img.shields.io/badge/Docs-Homebot-blue?style=flat&logo=readthedocs&logoColor=white" alt="Docs"></a>
  <a href="https://github.com/ysyisyourbrother/homebot/issues"><img src="https://img.shields.io/github/issues/ysyisyourbrother/homebot.svg" alt="Issues"></a>
  <a href="https://github.com/ysyisyourbrother/homebot/pulls"><img src="https://img.shields.io/github/issues-pr/ysyisyourbrother/homebot.svg" alt="GitHub pull requests"></a>
  <a href="https://github.com/ysyisyourbrother/homebot/stargazers"><img src="https://img.shields.io/github/stars/ysyisyourbrother/homebot.svg" alt="Stars"></a>
  <a href="https://github.com/ysyisyourbrother/homebot/network/members"><img src="https://img.shields.io/github/forks/ysyisyourbrother/homebot.svg" alt="Forks"></a>
  <a href="https://deepwiki.com/ysyisyourbrother/homebot"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
</p>

Homebot is a locally deployable personal AI agent designed for practical home automation. It connects conversational AI with everyday household tools while keeping the system lightweight, extensible, and easy to customize.

## Features

- **Natural voice interaction** with custom wake words, speaker verification, streaming speech recognition, and text-to-speech.
- **Multi-channel conversations** through Feishu, Telegram, and local voice input. Multiple channels can run in parallel with one shared Agent.
- **Flexible model providers** with support for OpenAI-compatible services, including DeepSeek, OpenRouter, Qwen, and Zhipu.
- **Smart-home skills** for tasks such as controlling Xiaomi Mi Home devices, playing music, checking weather, and searching Xiaohongshu.
- **Local-first deployment** that can run on an existing computer with a clear, modular architecture for personal customization.
- **Extensible tools and skills** for adding new integrations without changing the core conversation flow.

## Documentation

Installation, configuration, channels, tools and skills are documented at
**[ysyisyourbrother.github.io/homebot](https://ysyisyourbrother.github.io/homebot/)**.

Homebot runs on Python 3.11 or later. The documentation covers each supported
platform, including how to keep it running in the background and how to point
the voice channel at a specific microphone and speaker. See also the rest of
this README for what Homebot is and what it can do.

## Contact

Homebot is an open-source project under active development. Its goal is to build a simple, practical, and genuinely deployable solution for the smart-home domain.

For questions, ideas, or contribution proposals, contact [brandonye@foxmail.com](mailto:brandonye@foxmail.com).

## Contributors

Thanks to everyone who has contributed to Homebot.

<a href="https://github.com/ysyisyourbrother/homebot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ysyisyourbrother/homebot" alt="Homebot contributors">
</a>

## References & Acknowledgements

Homebot draws inspiration from the following open-source projects. We sincerely thank their authors and communities for making their work available.

- [nanobot](https://github.com/HKUDS/nanobot) — Homebot's early implementation was informed by nanobot's elegant agent design, which helped shape its initial direction.
- [OpenClaw](https://github.com/openclaw/openclaw)
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)

## Citation

If you find Homebot useful in your research, please consider citing:

```bibtex
@article{ye2026homebot,
  title={Homebot: A Personal AI Agent for Conversational Home Assistance and Automation},
  author={Ye, Shengyuan and Zhang, Yixin and Liang, Han and Zeng, Liekang and Du, Jiangsu and Yuan, Mu},
  journal={arXiv preprint arXiv:2608.02254},
  year={2026}
}
```
