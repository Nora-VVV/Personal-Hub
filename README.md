# Personal Hub · 每日科研与前沿情报看板

基于 **GitHub Actions + Python + OpenAlex/RSS + 大模型结构化拆解 + GitHub Pages** 搭建的零服务器个人情报工作台，支持一键导入 Obsidian（L2 轻量线索卡）。

## 覆盖领域
1. **电池与储能学术**：通过 OpenAlex 精准监控 Nature/Science/Cell 系、IEEE 电力电子与交通电气化系、Applied Energy / Energy / Energy Storage Materials 共 18 本期刊，过滤电池/电容预测预警与安全方向。
2. **AI 前沿**：Hugging Face Daily Papers、arXiv `cs.LG` 算法精选、Ahead of AI、Google DeepMind Blog。
3. **科学发现与 AI4S**：Nature News、Science News、Quanta Magazine、顶刊 AI4S 专题流。
4. **教育教学**：One Useful Thing、Inside Higher Ed、EDUCAUSE Review。
5. **储能产业**：Energy-Storage.News、Canary Media、IEA News。

## 日常维护（网页版直接改）
- **增删信息源或期刊**：编辑 `config/sources.yaml`
- **调整 AI 摘要风格或打分标准**：编辑 `config/prompt.txt`
- **手动触发一次抓取**：进入仓库顶部 `Actions` -> `Daily Brief Pipeline` -> `Run workflow`
