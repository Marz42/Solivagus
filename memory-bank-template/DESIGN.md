<!--
  此文件是 DESIGN.md 的空白模板，遵循 google-labs-code/design.md 格式。
  推荐使用 INIT_PROMPT 模式 G（设计器模式）通过 Agent 问答方式填充。

  激活方式：cp memory-bank-template/DESIGN.md DESIGN.md
  若项目无前端需求，无需创建此文件。DESIGN.md 不存在时所有相关检查自动跳过。
-->
---
name: ""
description: ""
colors:
  primary: ""
  secondary: ""
  tertiary: ""
  neutral: ""
typography:
  h1:
    fontFamily: ""
    fontSize: ""
  h2:
    fontFamily: ""
    fontSize: ""
  body:
    fontFamily: ""
    fontSize: ""
  caption:
    fontFamily: ""
    fontSize: ""
rounded:
  sm: ""
  md: ""
  lg: ""
spacing:
  sm: ""
  md: ""
  lg: ""
  xl: ""
---

## Overview

[TODO: 用 2-3 句话描述视觉设计理念和情感目标。例如："Architectural Minimalism meets Journalistic Gravitas. The UI evokes a premium matte finish — a high-end broadsheet or contemporary gallery."]

## Colors

[TODO: 描述每种颜色的用途和搭配规则。至少需要 primary（主色）、secondary（辅色）、tertiary（强调色/交互色）、neutral（底色）。可增加语义色如 success、error、warning。]

## Typography

[TODO: 描述字体层级选择逻辑。优先使用系统字体栈（如 system-ui, -apple-system）或 Google Fonts。说明各级标题和正文的字体、字号、粗细、行高。]

## Layout & Spacing

[TODO: 描述间距体系的使用原则，如 8px 栅格。定义 sm/md/lg/xl 的具体值和使用场景。]

## Elevation & Depth

[TODO（可选）: 描述阴影和层级体系，如 card/elevated/modal 的 box-shadow 值。]

## Shapes

[TODO（可选）: 描述圆角体系的使用原则，如按钮用小圆角、卡片用中圆角。]

## Components

[TODO: 定义 3-5 个核心组件的 token。引用上方定义的 colors 和 spacing tokens（如 {colors.primary}、{spacing.md}）。]

示例：

```yaml
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm} {spacing.md}"
  card:
    backgroundColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
```

## Do's and Don'ts

[TODO: 3-5 条使用原则。例如：
- ✅ DO: 使用 neutral 色作为主背景，primary 色仅用于标题
- ❌ DON'T: 在非交互元素上使用 tertiary 色，避免混淆用户]
