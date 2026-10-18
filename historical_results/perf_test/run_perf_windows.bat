@echo off
setlocal

REM 先把下面 URL 改成你项目当前真实的 POST 接口
if "%AGENT_URL%"=="" set AGENT_URL=http://127.0.0.1:8000/diagnose
if "%MODEL_LABEL%"=="" set MODEL_LABEL=int4

python perf_test\collect_env.py

python perf_test\benchmark_agent.py ^
  --url "%AGENT_URL%" ^
  --cases perf_test\perf_cases.jsonl ^
  --concurrency 1,5,10,20 ^
  --requests-per-level 100 ^
  --warmup 5 ^
  --timeout 120 ^
  --label "%MODEL_LABEL%"

echo.
echo Done. See perf_results\%MODEL_LABEL%\
endlocal
