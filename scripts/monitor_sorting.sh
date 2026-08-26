#!/bin/bash
# ============================================================
#  Dofbot Pro YOLOv11 3D视觉垃圾分拣 - 实时日志监控脚本
#  功能：实时查看所有节点运行日志 + 进程状态检测
#  使用方法：bash ~/monitor_sorting.sh
# ============================================================

LOG_DIR="/tmp/dofbot_logs"
PID_FILE="/tmp/dofbot_sorting_pids.txt"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # 无色

# 节点名称与对应颜色
declare -A NODE_COLORS=(
    ["camera"]="$BLUE"
    ["arm_driver"]="$GREEN"
    ["kinemarics"]="$YELLOW"
    ["msgToimg"]="$PURPLE"
    ["yolov11"]="$CYAN"
    ["yolov11_sortation"]="$RED"
)

show_help() {
    echo ""
    echo -e "${WHITE}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${WHITE}║  Dofbot Pro 分拣系统 - 日志监控与诊断工具   ║${NC}"
    echo -e "${WHITE}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo "用法: bash ~/monitor_sorting.sh [命令]"
    echo ""
    echo "命令:"
    echo "  all         实时跟踪所有节点日志（默认）"
    echo "  status      显示所有节点运行状态"
    echo "  camera      只看相机节点日志"
    echo "  arm         只看底层控制日志"
    echo "  ik          只看逆解程序日志"
    echo "  img         只看图像转换日志"
    echo "  yolo        只看YOLOv11识别日志"
    echo "  sort        只看分拣控制日志"
    echo "  last [N]    显示每个节点最近N行日志（默认20）"
    echo "  gpio        显示GPIO相关日志"
    echo "  error       只显示错误信息"
    echo "  topic       查看ROS2话题列表"
    echo "  node        查看ROS2节点列表"
    echo "  help        显示此帮助"
    echo ""
}

# ==================== 进程状态检查 ====================
show_status() {
    echo ""
    echo -e "${WHITE}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${WHITE}║            节点运行状态                      ║${NC}"
    echo -e "${WHITE}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    if [ ! -f "$PID_FILE" ] || [ ! -s "$PID_FILE" ]; then
        echo -e "  ${YELLOW}[!] 未找到PID记录，分拣系统可能未启动${NC}"
        echo "      请先运行: bash ~/start_sorting.sh"
        echo ""
        return
    fi

    local running=0
    local stopped=0

    printf "  %-6s  %-22s  %-10s  %-s\n" "PID" "节点名称" "状态" "运行时间"
    echo "  ────── ────────────────────── ────────── ──────────────"

    while read -r pid name; do
        if kill -0 "$pid" 2>/dev/null; then
            # 获取运行时间
            local etime
            etime=$(ps -p "$pid" -o etime= 2>/dev/null | xargs)
            local color="${NODE_COLORS[$name]:-$WHITE}"
            printf "  ${color}%-6s  %-22s  ${GREEN}%-10s${NC}  %-s\n" "$pid" "$name" "运行中" "$etime"
            ((running++))
        else
            printf "  ${RED}%-6s  %-22s  %-10s${NC}  %-s\n" "$pid" "$name" "已停止" "-"
            ((stopped++))
        fi
    done < "$PID_FILE"

    echo ""
    echo -e "  总计: ${GREEN}${running} 运行中${NC} | ${RED}${stopped} 已停止${NC}"

    # 显示日志文件大小
    echo ""
    echo "  日志文件:"
    echo "  ─────────────────────────────────────────"
    for logfile in "$LOG_DIR"/*.log; do
        if [ -f "$logfile" ]; then
            local size
            size=$(du -h "$logfile" 2>/dev/null | cut -f1)
            local lines
            lines=$(wc -l < "$logfile" 2>/dev/null)
            local basename
            basename=$(basename "$logfile")
            printf "  %-25s  %6s  %6d 行\n" "$basename" "$size" "$lines"
        fi
    done
    echo ""
}

# ==================== 实时跟踪所有日志 ====================
follow_all() {
    echo ""
    echo -e "${WHITE}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${WHITE}║       实时日志监控 (按 Ctrl+C 退出)          ║${NC}"
    echo -e "${WHITE}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  颜色说明: ${BLUE}相机${NC} | ${GREEN}驱动${NC} | ${YELLOW}逆解${NC} | ${PURPLE}图像${NC} | ${CYAN}YOLO${NC} | ${RED}分拣${NC}"
    echo ""

    # 检查日志文件是否存在
    local has_logs=false
    for logfile in "$LOG_DIR"/*.log; do
        if [ -f "$logfile" ]; then
            has_logs=true
            break
        fi
    done

    if [ "$has_logs" = false ]; then
        echo -e "  ${YELLOW}[!] 日志目录为空，分拣系统可能未启动${NC}"
        echo "      请先运行: bash ~/start_sorting.sh"
        return
    fi

    # 使用tail同时跟踪所有日志，并添加颜色前缀
    tail -f \
        "$LOG_DIR/camera.log" \
        "$LOG_DIR/arm_driver.log" \
        "$LOG_DIR/kinemarics.log" \
        "$LOG_DIR/msgToimg.log" \
        "$LOG_DIR/yolov11.log" \
        "$LOG_DIR/yolov11_sortation.log" \
        2>/dev/null | while IFS= read -r line; do
        case "$line" in
            *"==> "*camera*" <=="*)
                echo -e "${BLUE}────────── 相机 ──────────${NC}" ;;
            *"==> "*arm_driver*" <=="*)
                echo -e "${GREEN}────────── 底层控制 ──────────${NC}" ;;
            *"==> "*kinemarics*" <=="*)
                echo -e "${YELLOW}────────── 逆解程序 ──────────${NC}" ;;
            *"==> "*msgToimg*" <=="*)
                echo -e "${PURPLE}────────── 图像转换 ──────────${NC}" ;;
            *"==> "*yolov11.log*" <=="*)
                echo -e "${CYAN}────────── YOLOv11识别 ──────────${NC}" ;;
            *"==> "*yolov11_sortation*" <=="*)
                echo -e "${RED}────────── 机械臂分拣 ──────────${NC}" ;;
            *"[GPIO]"*)
                echo -e "${RED}[GPIO] ${line#*[GPIO]}${NC}" ;;
            *"[检测]"*)
                echo -e "${CYAN}${line}${NC}" ;;
            *"[重检测]"*)
                echo -e "${YELLOW}${line}${NC}" ;;
            *"[夹取]"*)
                echo -e "${GREEN}${line}${NC}" ;;
            *"[传送带]"*)
                echo -e "${PURPLE}${line}${NC}" ;;
            *"[分拣]"*)
                echo -e "${RED}${line}${NC}" ;;
            *"Error"*|*"error"*|*"ERROR"*|*"Traceback"*|*"Exception"*)
                echo -e "${RED}${line}${NC}" ;;
            *"Warning"*|*"warning"*|*"WARNING"*)
                echo -e "${YELLOW}${line}${NC}" ;;
            *)
                echo "$line" ;;
        esac
    done
}

# ==================== 跟踪单个节点 ====================
follow_single() {
    local logfile="$LOG_DIR/$1.log"
    local name=$2
    if [ ! -f "$logfile" ]; then
        echo -e "${YELLOW}[!] 日志文件不存在: $logfile${NC}"
        return
    fi
    echo ""
    echo -e "${WHITE}实时跟踪 ${name} 日志 (Ctrl+C 退出)${NC}"
    echo -e "${WHITE}文件: $logfile${NC}"
    echo "────────────────────────────────────────"
    tail -f "$logfile"
}

# ==================== 显示最近日志 ====================
show_last() {
    local n=${1:-20}
    echo ""
    echo -e "${WHITE}每个节点最近 ${n} 行日志:${NC}"

    for logfile in "$LOG_DIR"/*.log; do
        if [ -f "$logfile" ]; then
            local basename
            basename=$(basename "$logfile" .log)
            local color="${NODE_COLORS[$basename]:-$WHITE}"
            echo ""
            echo -e "${color}══════════ ${basename} ══════════${NC}"
            tail -"$n" "$logfile" 2>/dev/null
        fi
    done
    echo ""
}

# ==================== GPIO相关日志 ====================
show_gpio() {
    echo ""
    echo -e "${WHITE}GPIO 相关日志:${NC}"
    echo "────────────────────────────────────────"
    grep -h "GPIO\|BCM\|传送带\|conveyor" "$LOG_DIR"/*.log 2>/dev/null | tail -50
    if [ $? -ne 0 ]; then
        echo "  未找到GPIO相关日志"
    fi
    echo ""
}

# ==================== 错误日志 ====================
show_errors() {
    echo ""
    echo -e "${RED}错误日志:${NC}"
    echo "────────────────────────────────────────"
    grep -h -i "error\|exception\|traceback\|failed\|fatal" "$LOG_DIR"/*.log 2>/dev/null | tail -50
    if [ $? -ne 0 ]; then
        echo -e "  ${GREEN}未发现错误信息${NC}"
    fi
    echo ""
}

# ==================== ROS2诊断 ====================
show_topics() {
    echo ""
    echo -e "${WHITE}ROS2 话题列表:${NC}"
    echo "────────────────────────────────────────"
    source /opt/ros/humble/setup.bash
    source "$HOME/dofbot_pro_ws/install/setup.bash" 2>/dev/null
    ros2 topic list 2>/dev/null
    echo ""
}

show_nodes() {
    echo ""
    echo -e "${WHITE}ROS2 节点列表:${NC}"
    echo "────────────────────────────────────────"
    source /opt/ros/humble/setup.bash
    source "$HOME/dofbot_pro_ws/install/setup.bash" 2>/dev/null
    ros2 node list 2>/dev/null
    echo ""
}

# ==================== 主入口 ====================
case "${1:-all}" in
    all)        follow_all ;;
    status|st)  show_status ;;
    camera|cam) follow_single "camera" "相机节点" ;;
    arm)        follow_single "arm_driver" "底层控制" ;;
    ik)         follow_single "kinemarics" "逆解程序" ;;
    img)        follow_single "msgToimg" "图像转换" ;;
    yolo)       follow_single "yolov11" "YOLOv11识别" ;;
    sort)       follow_single "yolov11_sortation" "机械臂分拣" ;;
    last)       show_last "${2:-20}" ;;
    gpio)       show_gpio ;;
    error|err)  show_errors ;;
    topic)      show_topics ;;
    node)       show_nodes ;;
    help|-h)    show_help ;;
    *)          echo "未知命令: $1"; show_help ;;
esac
