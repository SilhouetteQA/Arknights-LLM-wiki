"""Agent 服务入口 — python -m arknights_wiki.agent.server 的替代方式"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("arknights_wiki.agent.server:app", host="0.0.0.0", port=8000, reload=False)
