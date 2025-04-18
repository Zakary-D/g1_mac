from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import uuid
import random
import io
import random, math
from sqlalchemy import Boolean

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # 请更换为更安全的密钥
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///poker_tournament.db'  # 使用 SQLite 数据库引擎在当前项目根目录下生成一个持久化的 .db 文件
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ----------------------
# 数据库模型定义
# ----------------------

class Player(db.Model):
    """
    选手信息模型，记录姓名、手机号、唯一编号，以及每轮的积分
    """
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(5), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    score_round1 = db.Column(db.Float, default=0)
    score_round2 = db.Column(db.Float, default=0)
    score_round3 = db.Column(db.Float, default=0)
    chips_round1 = db.Column(db.Integer, default=0)
    chips_round2 = db.Column(db.Integer, default=0)
    is_dummy = db.Column(Boolean, default=False)
    
    def total_score(self):
        return self.score_round1 + self.score_round2

    @property
    def chips_sum(self):
        return (self.chips_round1 or 0) + (self.chips_round2 or 0)

    @property
    def chip_diff(self):
        return abs((self.chips_round1 or 0) - (self.chips_round2 or 0))

class TableAssignment(db.Model):
    """
    桌次分配记录，每条记录表示某一轮某桌中某座位分配给哪个选手。
    round_number: 轮次 (1,2,3)
    table_number: 桌子编号（例如第一桌、第二桌…）
    seat_number: 桌内编号（1-8）
    """
    id = db.Column(db.Integer, primary_key=True)
    round_number = db.Column(db.Integer, nullable=False)
    table_number = db.Column(db.Integer, nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    player = db.relationship('Player')

class Judge(db.Model):
    """
    裁判账号模型，示例中只使用明文密码（实际使用时请对密码进行哈希加密）
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    
class Elimination(db.Model):
    """
    第三轮淘汰记录，每记录一条淘汰的信息，包括淘汰顺序和选手ID
    """
    id = db.Column(db.Integer, primary_key=True)
    round_number = db.Column(db.Integer, nullable=False)
    table_number = db.Column(db.Integer, nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    elimination_order = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Float, nullable=False)
    player = db.relationship('Player')

class JudgeSubmission(db.Model):
    """
    裁判录入记录：
      - round_number, table_number, judge_username
      - 每个座位的筹码(chip_1 ~ chip_8)与计算后的积分(score_1 ~ score_8)
      - 记录录入的修改（例如选手编号修改）可通过提交时的表单数据体现
    """
    id = db.Column(db.Integer, primary_key=True)
    round_number = db.Column(db.Integer, nullable=False)
    table_number = db.Column(db.Integer, nullable=False)
    judge_username = db.Column(db.String(30), nullable=False)

    # 存储每座位的“最终确定”的选手ID
    seat1_player_id = db.Column(db.Integer, nullable=True)
    seat2_player_id = db.Column(db.Integer, nullable=True)
    seat3_player_id = db.Column(db.Integer, nullable=True)
    seat4_player_id = db.Column(db.Integer, nullable=True)
    seat5_player_id = db.Column(db.Integer, nullable=True)
    seat6_player_id = db.Column(db.Integer, nullable=True)
    seat7_player_id = db.Column(db.Integer, nullable=True)
    seat8_player_id = db.Column(db.Integer, nullable=True)

    # 保存每个座位的筹码值和积分
    chip_1 = db.Column(db.Integer, nullable=True)
    chip_2 = db.Column(db.Integer, nullable=True)
    chip_3 = db.Column(db.Integer, nullable=True)
    chip_4 = db.Column(db.Integer, nullable=True)
    chip_5 = db.Column(db.Integer, nullable=True)
    chip_6 = db.Column(db.Integer, nullable=True)
    chip_7 = db.Column(db.Integer, nullable=True)
    chip_8 = db.Column(db.Integer, nullable=True)
    score_1 = db.Column(db.Float, nullable=True)
    score_2 = db.Column(db.Float, nullable=True)
    score_3 = db.Column(db.Float, nullable=True)
    score_4 = db.Column(db.Float, nullable=True)
    score_5 = db.Column(db.Float, nullable=True)
    score_6 = db.Column(db.Float, nullable=True)
    score_7 = db.Column(db.Float, nullable=True)
    score_8 = db.Column(db.Float, nullable=True)
    # 你也可以记录提交时间等信息

# ----------------------
# 初始化数据库及创建默认数据
# ----------------------
@app.before_request
def initialize_once():
    if not hasattr(app, 'initialized'):
        create_tables()  # 仅在第一次请求时调用一次初始化函数
        app.initialized = True

# @app.before_first_request
def create_tables():
    db.create_all()
    # # 如果不存在默认裁判账号，则创建一个默认账号（用户名 judge1, 密码 password）
    # if not Judge.query.filter_by(username='judge001').first():
    #     judge = Judge(username='judge001', password='password')
    #     db.session.add(judge)
    #     db.session.commit()

    # 如果没有默认超级裁判账号judge044，则创建（以及其他初始账号可在单独路由生成）
    if not Judge.query.filter_by(username='judge044').first():
        super_judge = Judge(username='judge044', password='password123')
        db.session.add(super_judge)
        db.session.commit()

# ----------------------
# 辅助函数：分桌、积分计算
# ----------------------
def assign_tables(players, round_number):
    """
    分桌操作：
      - 第一轮：按选手导入后分配的随机编号排序分桌（1~8为第一桌，9~16为第二桌……）。
      - 第二轮：基于第一轮累计积分（score_round1）排序重新分桌（不淘汰），并保留第一轮数据。
      - 第三轮：从前两轮累计积分中取前8名（积分清零后），分为一桌。
    """
    # 清除此轮以前的分桌记录
    # TableAssignment.query.filter_by(round_number=round_number).delete()
    # db.session.commit()


    # 筛选出该轮尚未分桌的选手（避免重复分配）
    assigned_ids = {a.player_id for a in TableAssignment.query.filter_by(round_number=round_number).all()}
    unassigned = [p for p in players if p.id not in assigned_ids]
    
    total_target = 104

    if round_number in (1,2):
        # 1. 计算 normal 与 carrots
        normal = [p for p in players if int(p.unique_id) < 200]
        total = len(normal)
        target_slots = 13 * 8   # 固定 104
        carrots_num = max(0, target_slots - total)

        # 2. 补萝卜
        next_id = 200
        carrots = []
        while len(carrots) < carrots_num:
            uid = str(next_id)
            if not Player.query.filter_by(unique_id=uid).first():
                dummy = Player(unique_id=uid, name=f"萝卜{uid}", phone=f"fake12138", is_dummy=True)
                db.session.add(dummy)
                db.session.flush()
                carrots.append(dummy)
            next_id += 1
        db.session.commit()

        # 3. 排序 normal
        if round_number == 1:
            normal.sort(key=lambda p: int(p.unique_id))
        else:
            normal.sort(key=lambda p: p.score_round1, reverse=True)

        real = [p for p in players if not p.is_dummy]

        # 4. 分配 carrots_per_table
        base, extra = divmod(carrots_num, 13)
        # extra 个桌多一个，从 13,12,... 向上分配
        cpts = [base] * 13
        for i in range(extra):
            cpts[12 - i] += 1

        # 5. 构造每桌成员列表
        assignments = []
        idx = 0
        c_idx = 0
        for table in range(1,14):
            n_slots = 8 - cpts[table-1]
            # 取 normal
            for _ in range(n_slots):
                p = normal[idx]
                assignments.append((table, p.id))
                idx += 1
            # 取 carrots
            for _ in range(cpts[table-1]):
                dummy = carrots[c_idx]
                assignments.append((table, dummy.id))
                c_idx += 1

        # 6. 写入 TableAssignment
        for table, pid in assignments:
            seat = TableAssignment(
                round_number=round_number,
                table_number=table,
                seat_number=(len(TableAssignment.query.filter_by(round_number=round_number, table_number=table).all())+1),
                player_id=pid
            )
            db.session.add(seat)
        db.session.commit()

    elif round_number == 3:
        # 多条件排序
        def key_fn(p):
            return (
                -(p.score_round1 + p.score_round2),
                -(p.chips_round1 + p.chips_round2),
                abs((p.chips_round1 or 0) - (p.chips_round2 or 0)),
                int(p.unique_id)
            )
        sorted_ps = sorted(players, key=key_fn)
        top8 = sorted_ps[:8]

        # 检查第8、9名是否完全同分
        if len(players) > 8 and key_fn(sorted_ps[7]) == key_fn(sorted_ps[8]):
            raise RuntimeError(
                "第8、9名在 积分／筹码总和／筹码差／编号 上完全相同，"
                "请手动掷骰子决定谁进入第三轮。"
            )

        # 清零第三轮积分，分到1号桌
        for p in top8:
            p.score_round3 = 0
            db.session.add(p)
        db.session.commit()

        # 写入 assignment
        for seat_no, p in enumerate(top8, start=1):
            ta = TableAssignment(
                round_number=3,
                table_number=1,
                seat_number=seat_no,
                player_id=p.id
            )
            db.session.add(ta)
        db.session.commit()

        # # 第三轮只选前8人；重置 round3 分数
        # sorted_players = sorted(players, key=lambda p: (-p.total_score(), int(p.unique_id)))
        # # 第8名的得分
        # if len(sorted_players) >= 8:
        #     score_cutoff = sorted_players[7].total_score()
        # else:
        #     score_cutoff = sorted_players[-1].total_score()

        # # 找出所有得分 >= 第8名分数的玩家，再取其中编号小的前8个
        # candidates = [p for p in sorted_players if p.total_score() >= score_cutoff]
        # unassigned = sorted(candidates, key=lambda p: (-p.total_score(), int(p.unique_id)))[:8]

        # # 考虑是否已有分桌数据，本轮理论上只有一桌
        # unassigned = [p for p in sorted_players if p.id not in assigned_ids]
        # 清除旧的第三轮分桌数据（防止重复生成）
        # TableAssignment.query.filter_by(round_number=3).delete()
    
        # for p in unassigned:
        #     p.score_round3 = 0
        # db.session.commit()
    else:
        return

    # table_size = 8
    # assignments = []
    # # 按每 8 人一桌
    # for index, player in enumerate(unassigned):
    #     table_number = index // table_size + 1
    #     seat_number = index % table_size + 1
    #     assignment = TableAssignment(
    #         round_number=round_number,
    #         table_number=table_number,
    #         seat_number=seat_number,
    #         player_id=player.id
    #     )
    #     assignments.append(assignment)
    # db.session.bulk_save_objects(assignments)
    # db.session.commit()

@app.route('/start_round/<int:round_number>')
def start_round(round_number):
    """
    仅超级裁判可点击“进入第X轮”后触发的分桌逻辑
    """
    if 'judge' not in session or session['judge'] != 'judge044':
        flash("没有权限操作此功能")
        return redirect(url_for('judge_dashboard'))
    
    if round_number not in [2, 3]:
        flash("无效的轮次")
        return redirect(url_for('judge_dashboard'))
    
    # 取所有选手
    players = Player.query.all()
    # 调用你的分桌函数
    assign_tables(players, round_number)  # 保留第一轮记录，不覆盖
    flash(f"已成功开始第 {round_number} 轮，并完成分桌！")
    return redirect(url_for('view_tables', round_number=round_number))

def calculate_elimination_score(elimination_order):
    """
    根据淘汰顺序计算淘汰选手的固定得分。
    淘汰顺序从 1 开始表示第一个淘汰的选手
    固定分数由下表定义：
      排名 1: 25, 2: 20, 3: 16, 4: 12, 5: 9, 6: 6, 7: 3, 8: 0
    对于淘汰顺序 n，则该选手在8人桌中的排名为 8 - n + 1。
    """
    points = {1: 25, 2: 20, 3: 16, 4: 12, 5: 9, 6: 6, 7: 3, 8: 0}
    rank = 8 - elimination_order + 1
    return points.get(rank, 0)


def calculate_score_from_chips(chip_list, remaining_count):
    """
    根据在场选手的筹码分布计算额外积分分配。

    参数：
      chip_list: 长度为8的列表，表示按照桌内座位顺序录入的筹码数，
                 其中前 remaining_count 个有效（剩余在场选手），其余忽略。
      remaining_count: 在场（未淘汰）的选手数量（>=2）。

    返回：
      一个列表，包含每个有效选手的最终得分（剩余座位没有选手时记为0）。
    """
    # 固定积分映射
    points = {1: 25, 2: 20, 3: 16, 4: 12, 5: 9, 6: 6, 7: 3, 8: 0}
    if remaining_count < 2:
        # 只有一人时，该人获得25分
        return [25] + [0]*(len(chip_list)-1)
    
    # 基础分：取剩余人数对应的分值（例如，3人时基础分为 第3名分数，即16分；2人时基础分为20）
    base = points[remaining_count]
    
    # 计算额外可分配积分：
    extra_total = 0
    for i in range(1, remaining_count):
        extra_total += (points[i] - base)
    # 计算剩余在场选手总筹码
    valid_chips = chip_list[:remaining_count]
    total_chips = sum(valid_chips)
    
    scores = []
    for i in range(len(chip_list)):
        if i < remaining_count:
            # 如果筹码总量为0，则均分为0
            if total_chips > 0:
                extra = (chip_list[i] / total_chips) * extra_total
            else:
                extra = 0
            score = base + extra
            score = min(score, 25)  # 不超过25分
            scores.append(score)
        else:
            scores.append(0)
    return scores


# ----------------------
# 各种路由（页面）定义
# ----------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_roster', methods=['GET', 'POST'])
def upload_roster():
    if request.method == 'POST':
        file = request.files['file']
        if file:
            try:
                df = pd.read_excel(file)
                if '姓名' not in df.columns or '手机号' not in df.columns:
                    flash("Excel 必须包含 ‘姓名’ 和 ‘手机号’ 两列")
                    return redirect(request.url)

                # 将所有选手打包到一个列表
                raw_players = []
                for _, row in df.iterrows():
                    name = row['姓名']
                    phone = str(row['手机号'])
                    if Player.query.filter_by(phone=phone).first():
                        continue  # 避免重复手机号
                    raw_players.append({'name': name, 'phone': phone})

                if len(raw_players) > 999:
                    flash("选手数量不能超过 999")
                    return redirect(request.url)

                # 打乱顺序，生成随机编号（001 ~ N）
                random.shuffle(raw_players)
                inserted_players = []
                for idx, player_data in enumerate(raw_players):
                    unique_id = str(idx + 1).zfill(3)  # 生成编号 001~104
                    player = Player(unique_id=unique_id, name=player_data['name'], phone=player_data['phone'])
                    db.session.add(player)
                    inserted_players.append(player)
                db.session.commit()

                # ✅ 按编号排序，顺序分桌（桌号、座位号）
                # players = Player.query.order_by(Player.unique_id).all()
                # TableAssignment.query.filter_by(round_number=1).delete()
                # db.session.commit()
                # assignments = []
                # for index, player in enumerate(players):
                #     table_number = index // 8 + 1
                #     seat_number = index % 8 + 1
                #     assignment = TableAssignment(
                #         round_number=1,
                #         table_number=table_number,
                #         seat_number=seat_number,
                #         player_id=player.id
                #     )
                #     assignments.append(assignment)
                # db.session.bulk_save_objects(assignments)
                # db.session.commit()

                # flash(f"导入成功，共 {len(inserted_players)} 名选手，已随机编号并完成第一轮分桌")
                # print(f"导入成功，共 {len(inserted_players)} 名选手，已随机编号并完成第一轮分桌")
                # print(inserted_players)
                # print(raw_players)
                # return redirect(url_for('view_tables', round_number=1))

                # 进行第一轮分桌，按编号升序分桌（保证 1~8 分配到第一桌等）
                players = Player.query.order_by(Player.unique_id).all()
                # 注意：不删除其他轮次记录，第一轮新分桌只为未分桌选手分配
                assign_tables(players, round_number=1)
                flash(f"成功导入 {len(inserted_players)} 名选手，并已第一轮分桌完成")
                return redirect(url_for('view_tables', round_number=1))
            
            except Exception as e:
                flash("导入失败：" + str(e))
                return redirect(request.url)
    return render_template('upload_roster.html')

# @app.route('/round/<int:round_number>/assign')
# def assign_round(round_number):
#     """
#     手动触发指定轮次的桌次分配。
#     根据轮次规则重新分配桌位，并生成 TableAssignment 记录。
#     """
#     players = Player.query.all()
#     if round_number not in [1, 2, 3]:
#         flash("无效的轮次")
#         return redirect(url_for('index'))
#     assign_tables(players, round_number)
#     flash(f"成功为第 {round_number} 轮进行桌次分配！")
#     return redirect(url_for('view_tables', round_number=round_number))

@app.route('/round/<int:round_number>/tables')
def view_tables(round_number):
    """
    查看某轮的桌次分配情况，显示桌号、座位号、选手姓名及其唯一编号。
    """
    assignments = TableAssignment.query.filter_by(round_number=round_number)\
                        .order_by(TableAssignment.table_number, TableAssignment.seat_number).all()
    return render_template('view_tables.html', assignments=assignments, round_number=round_number)

# ---------- 裁判登录及操作 --------------

@app.route('/judge/login', methods=['GET', 'POST'])
def judge_login():
    """
    裁判登录页面，登录成功后进入裁判工作台。
    （注意：示例中未对密码进行加密）
    """
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        judge = Judge.query.filter_by(username=username, password=password).first()
        if judge:
            session['judge'] = judge.username
            flash("登录成功")
            return redirect(url_for('judge_dashboard'))
        else:
            flash("用户名或密码错误")
    return render_template('judge_login.html')

@app.route('/judge/logout')
def judge_logout():
    session.pop('judge', None)
    flash("已退出登录")
    return redirect(url_for('index'))

@app.route('/judge/dashboard')
def judge_dashboard():
    """
    裁判工作台页面，裁判可以选择录入每桌筹码数，
    或者进入第三轮淘汰记录页面。
    """
    if 'judge' not in session:
        flash("请先登录")
        return redirect(url_for('judge_login'))
    
    assignments_round2_exist = TableAssignment.query.filter_by(round_number=2).first() is not None
    return render_template('judge_dashboard.html',
                           assignments_round2_exist=assignments_round2_exist)
    # return render_template('judge_dashboard.html')

@app.route('/judge/submit', methods=['GET'])
def judge_submit():
    if 'judge' not in session:
        flash("请先登录裁判账号")
        return redirect(url_for('judge_login'))
    
    round_number = int(request.args.get('round_number', 1))
    table_number = int(request.args.get('table_number', 1))

    # 非超级裁判只能录入自己对应桌
    if session['judge'] != 'judge044':
        allowed_table = int(session['judge'].replace('judge',''))
        if table_number != allowed_table:
            flash("无权录入其他桌的数据")
            return redirect(url_for('judge_dashboard'))
        # 新增：只能录入当前进行中的轮次
        latest_round = 1
        if TableAssignment.query.filter_by(round_number=2).count() > 0:
            latest_round = 2
        if TableAssignment.query.filter_by(round_number=3).count() > 0:
            latest_round = 3
        if round_number != latest_round:
            flash(f"⚠️ 当前只允许录入第 {latest_round} 轮，您选择了第 {round_number} 轮")
            return redirect(url_for('judge_dashboard'))

    
    # 查询数据库，获取本桌8个座位分配情况
    assignments = TableAssignment.query.filter_by(round_number=round_number, table_number=table_number)\
                       .order_by(TableAssignment.seat_number).all()
    seat_info = []
    for seat_num in range(1,9):
        # 默认空
        seat_info.append({"seat": seat_num, "unique_id": "", "name": "", "chips": 0})
    for a in assignments:
        seat_idx = a.seat_number - 1
        if a.player is None:
            continue
        seat_info[seat_idx]["unique_id"] = a.player.unique_id
        seat_info[seat_idx]["name"] = a.player.name
    
    return render_template('judge_submit.html',
                           round_number=round_number,
                           table_number=table_number,
                           seat_info=seat_info)

# 接收前端提交的最终积分，然后写入数据库，前端在“确认提交”时，会把座位信息（含选手编号、最终积分、是否淘汰等）打包成 JSON，提交到 finalize_scores；
@app.route('/judge/finalize_scores', methods=['POST'])
def finalize_scores():
    print(1)
    if 'judge' not in session:
        flash("请先登录裁判账号")
        return redirect(url_for('judge_login'))
    

    if session['judge'] != 'judge044':
        judge_number = int(session['judge'].replace('judge',''))

        if table_number != judge_number:
            flash("无权提交其他桌的数据")
            return redirect(url_for('judge_dashboard'))

        # 校验是否为当前轮次
        latest_round = 1
        if TableAssignment.query.filter_by(round_number=2).count() > 0:
            latest_round = 2
        if TableAssignment.query.filter_by(round_number=3).count() > 0:
            latest_round = 3

        if round_number != latest_round:
            flash(f"⚠️ 当前只允许录入第 {latest_round} 轮，您提交了第 {round_number} 轮")
            return redirect(url_for('judge_dashboard'))

    round_number = int(request.form['round_number'])
    table_number = int(request.form['table_number'])
    seats_json = request.form.get('seats_data')  # JSON string

    import json
    seats_data = json.loads(seats_json)  # list of {seat, unique_id, score, eliminated...}
    
    # 用于记录操作
    judge_username = session['judge']
    chips = []
    new_ids = []
    seat_player_ids = []

    for sd in seats_data:
        unique_id = sd["unique_id"]
        player = Player.query.filter_by(unique_id=unique_id).first()
        if player:
            seat_player_ids.append(player.id)
        else:
            seat_player_ids.append(None)  # 空座位或预留位

    for seat in range(1, 9):
        try:
            chip_value = int(request.form.get(f'chip_{seat}', 0))
        except ValueError:
            chip_value = 0
        chips.append(chip_value)

        # 若裁判对某座位修改了选手编号，则接收（允许为空）
        new_id = request.form.get(f'player_id_{seat}', '').strip()
        new_ids.append(new_id)

    # 先建立一条 JudgeSubmission 记录 (表示本次操作)
    submission = JudgeSubmission(
        round_number=round_number,
        table_number=table_number,
        judge_username=judge_username,
        # 在 JudgeSubmission 中，你有 chip_1..8, score_1..8 等字段需要赋值
        # 这里我们先全部填 0，后面再按 seats_data 填对应seat
        chip_1=0, chip_2=0, chip_3=0, chip_4=0,
        chip_5=0, chip_6=0, chip_7=0, chip_8=0,
        score_1=0, score_2=0, score_3=0, score_4=0,
        score_5=0, score_6=0, score_7=0, score_8=0,
        # seat1_player_id = new_ids[0],
        # seat2_player_id = new_ids[1],
        # seat3_player_id = new_ids[2],
        # seat4_player_id = new_ids[3],
        # seat5_player_id = new_ids[4],
        # seat6_player_id = new_ids[5],
        # seat7_player_id = new_ids[6],
        # seat8_player_id = new_ids[7]
        seat1_player_id = seat_player_ids[0],
        seat2_player_id = seat_player_ids[1],
        seat3_player_id = seat_player_ids[2],
        seat4_player_id = seat_player_ids[3],
        seat5_player_id = seat_player_ids[4],
        seat6_player_id = seat_player_ids[5],
        seat7_player_id = seat_player_ids[6],
        seat8_player_id = seat_player_ids[7],
    )
    db.session.add(submission)
    # db.session.commit()  # 先 commit 以获取 submission.id
    
    # 我们把 seats_data 按 seat 顺序填进 submission 的 chip_x, score_x
    # 如果需要记录筹码，可在前端 seats_data 里也带上 chips
    # 这里假设 seats_data 里有 "chips" 字段
    # 先构造一个 seat->(chips, score) dict 方便赋值
    seat_map = {}
    for sd in seats_data:
        seat_idx = sd["seat"]
        # seat_idx in [1..8]
        seat_map[seat_idx] = sd
    
    # 准备写入 submission
    def set_submission_fields(sub, seat_no, chip_val, score_val):
        if seat_no == 1:
            sub.chip_1 = chip_val
            sub.score_1 = score_val
        elif seat_no == 2:
            sub.chip_2 = chip_val
            sub.score_2 = score_val
        elif seat_no == 3:
            sub.chip_3 = chip_val
            sub.score_3 = score_val
        elif seat_no == 4:
            sub.chip_4 = chip_val
            sub.score_4 = score_val
        elif seat_no == 5:
            sub.chip_5 = chip_val
            sub.score_5 = score_val
        elif seat_no == 6:
            sub.chip_6 = chip_val
            sub.score_6 = score_val
        elif seat_no == 7:
            sub.chip_7 = chip_val
            sub.score_7 = score_val
        elif seat_no == 8:
            sub.chip_8 = chip_val
            sub.score_8 = score_val

    for seat_no in range(1,9):
        if seat_no not in seat_map:
            continue
        sd = seat_map[seat_no]
        score_f = float(sd["score"])
        # 如果 seats_data 里也带了 "chips" 字段:
        chip_val = int(sd["chips"]) if "chips" in sd else 0
        
        # 写入 submission
        set_submission_fields(submission, seat_no, chip_val, score_f)
        
        # 再写入 Player 表
        uid = sd["unique_id"]
        if uid:
            player = Player.query.filter_by(unique_id=uid).first()
            if player:
                if round_number == 1:
                    player.score_round1 += score_f
                    player.chips_round1 += chip_val
                elif round_number == 2:
                    player.score_round2 += score_f
                    player.chips_round2 += chip_val
                elif round_number == 3:
                    player.score_round3 += score_f
    
    db.session.commit()
    
    flash("✅ 本轮积分已确认提交并记录！")
    return redirect(url_for('judge_dashboard'))

# @app.route('/judge/eliminate', methods=['POST'])
# def judge_eliminate():
#     if 'judge' not in session:
#         flash("请先登录裁判账号")
#         return redirect(url_for('judge_login'))
#     round_number = int(request.form['round_number'])
#     table_number = int(request.form['table_number'])
#     player_unique_id = request.form['player_unique_id'].strip()
    
#     # 权限检查：普通裁判只能操作自己桌
#     if session['judge'] != 'judge044':
#         allowed_table = int(session['judge'].replace('judge',''))
#         if table_number != allowed_table:
#             flash("无权操作其他桌数据")
#             return redirect(url_for('judge_dashboard'))
    
#     player = Player.query.filter_by(unique_id=player_unique_id).first()
#     if not player:
#         flash("找不到选手")
#         return redirect(url_for('judge_submit', round_number=round_number, table_number=table_number))
    
#     # 统计当前该桌已淘汰人数，决定淘汰顺序
#     current_elim_count = Elimination.query.filter_by(round_number=round_number, table_number=table_number).count()
#     elimination_order = current_elim_count + 1
#     fixed_score = calculate_elimination_score(elimination_order)
    
#     elimination = Elimination(
#         round_number=round_number,
#         table_number=table_number,
#         player_id=player.id,
#         elimination_order=elimination_order,
#         score=fixed_score
#     )
#     db.session.add(elimination)
    
#     # 更新该选手本轮得分为固定分
#     if round_number == 1:
#         player.score_round1 += fixed_score
#     elif round_number == 2:
#         player.score_round2 += fixed_score
#     elif round_number == 3:
#         player.score_round3 += fixed_score
#     db.session.commit()
#     flash(f"淘汰成功：{player.unique_id} - {player.name} 固定得分 {fixed_score}")
#     return redirect(url_for('judge_submit', round_number=round_number, table_number=table_number))


# 超级裁判可以撤销某个裁判的录入记录
@app.route('/judge/revoke/<int:submission_id>')
def judge_revoke(submission_id):
    if 'judge' not in session or session['judge'] != "judge044":
        flash("没有权限")
        return redirect(url_for('judge_dashboard'))
    sub = JudgeSubmission.query.get(submission_id)
    print(submission_id)
    print(sub)
    if sub:
        round_number = sub.round_number
        # 回退seat1~8的积分
        seat_player_ids = [
            sub.seat1_player_id,
            sub.seat2_player_id,
            sub.seat3_player_id,
            sub.seat4_player_id,
            sub.seat5_player_id,
            sub.seat6_player_id,
            sub.seat7_player_id,
            sub.seat8_player_id
        ]
        seat_scores = [
            sub.score_1,
            sub.score_2,
            sub.score_3,
            sub.score_4,
            sub.score_5,
            sub.score_6,
            sub.score_7,
            sub.score_8
        ]
        # 对每个seat，找到对应player并把积分减掉
        for i in range(8):
            p_id = seat_player_ids[i]
            sc = seat_scores[i]
            print(p_id, sc)
            if p_id is not None and sc is not None:  # 如果有玩家ID且积分不为0
                player = Player.query.get(p_id)
                if player:
                    if round_number == 1:
                        player.score_round1 -= sc
                    elif round_number == 2:
                        player.score_round2 -= sc
                    elif round_number == 3:
                        player.score_round3 -= sc
        db.session.delete(sub)
        db.session.commit()

        flash("撤销成功，积分已回退")
    else:
        flash("未找到对应记录")

    return redirect(url_for('judge_view_submissions'))

@app.route('/judge/view_submissions')
def judge_view_submissions():
    # 1) 检查是否是超级裁判
    if 'judge' not in session or session['judge'] != 'judge044':
        flash("只有超级裁判可查看所有录入记录")
        return redirect(url_for('judge_dashboard'))
    
    # 2) 查询所有录入记录
    submissions = JudgeSubmission.query.order_by(JudgeSubmission.round_number,
                                                 JudgeSubmission.table_number,
                                                 JudgeSubmission.id).all()
    # 3) 传给模板
    return render_template('judge_view_submissions.html', submissions=submissions)


@app.route('/add_player_manual', methods=['POST'])
def add_player_manual():
    if 'judge' not in session or session['judge'] != 'judge044':
        flash("无权限操作")
        return redirect(url_for('index'))

    unique_id = request.form['unique_id'].strip()
    name = request.form['name'].strip()
    phone = request.form['phone'].strip()

    if not unique_id or not name or not phone:
        flash("请输入完整信息")
        return redirect(url_for('manage_players'))

    if Player.query.filter_by(unique_id=unique_id).first():
        flash("编号已存在")
        return redirect(url_for('manage_players'))

    if Player.query.filter_by(phone=phone).first():
        flash("手机号已存在")
        return redirect(url_for('manage_players'))

    new_player = Player(unique_id=unique_id, name=name, phone=phone)
    db.session.add(new_player)
    db.session.commit()
    flash("添加成功")
    return redirect(url_for('manage_players'))


@app.route('/delete_player_manual', methods=['POST'])
def delete_player_manual():
    if 'judge' not in session or session['judge'] != 'judge044':
        flash("无权限操作")
        return redirect(url_for('index'))

    player_id = request.form['delete_id']
    player = Player.query.get(player_id)
    if player:
        db.session.delete(player)
        db.session.commit()
        flash("删除成功")
    else:
        flash("选手不存在")

    return redirect(url_for('manage_players'))

@app.route('/manage_players', methods=['GET', 'POST'])
def manage_players():
    if 'judge' not in session or session['judge'] != 'judge044':
        flash("无权限访问")
        return redirect(url_for('index'))

    players = Player.query.order_by(Player.unique_id).all()

    return render_template('manage_players.html', players=players)

# ---------- 选手查询 --------------

# 选手查询（根据手机号或编号查询分桌信息）
@app.route('/player/query', methods=['GET', 'POST'])
def player_query():
    data = None
    if request.method == 'POST':
        identifier = request.form['identifier'].strip()
        # 允许输入手机号或选手唯一编号
        player = Player.query.filter((Player.phone==identifier) | (Player.unique_id==identifier)).first()
        if player:
            # 查询三轮的分桌信息
            all_rounds_info = []
            for r in [1, 2, 3]:
                # 是否有该轮分配记录
                assignment = TableAssignment.query.filter_by(round_number=r, player_id=player.id).first()
                if assignment:
                    all_rounds_info.append({
                        'round': r,
                        'table_number': assignment.table_number,
                        'seat_number': assignment.seat_number
                    })
                else:
                    all_rounds_info.append({
                        'round': r,
                        'table_number': '未分桌',
                        'seat_number': '未分桌'
                    })

            data = {
                'unique_id': player.unique_id,
                'name': player.name,
                'rounds': all_rounds_info
            }
        else:
            flash("没有找到对应选手")
    return render_template('player_query.html', data=data)

# ---------- 排行榜 --------------

# 排行榜展示（前两轮累计，第三轮独立）
@app.route('/scoreboard/<int:round_number>')
def scoreboard(round_number):
    print("scoreboard")
    if round_number == 1:
        # 第一轮只看 score_round1
        players = Player.query.all()
        scoreboard_data = []
        for p in players:
            scoreboard_data.append({
                'unique_id': p.unique_id,
                'name': p.name,
                'score': p.score_round1
            })
        # 按第一轮积分降序
        scoreboard_data.sort(key=lambda x: x['score'], reverse=True)
        title = "第一轮积分榜 (仅第一轮)"
        
    elif round_number == 2:
        # 第二轮看前两轮累计 (score_round1 + score_round2)
        players = Player.query.all()
        scoreboard_data = []
        for p in players:
            total_score = p.score_round1 + p.score_round2
            scoreboard_data.append({
                'unique_id': p.unique_id,
                'name': p.name,
                'score': total_score
            })
        scoreboard_data.sort(key=lambda x: x['score'], reverse=True)
        title = "第二轮积分榜 (前两轮累计)"
    elif round_number == 3:
            """
            第三轮排行榜：
            - 包括已淘汰选手（他们的得分固定为淘汰时计算的分数），以及
            - 还未淘汰的剩余选手（通过筹码录入计算得分）
            两部分按得分降序排列显示
            """
            # 查询淘汰记录（假设已经按淘汰顺序记录好得分）
            eliminated = Elimination.query.filter_by(round_number=3).all()
            eliminated_data = [{
                'unique_id': e.player.unique_id,
                'name': e.player.name,
                'score': e.score,
                'order': e.elimination_order
            } for e in eliminated]

            # 查询仍在场的选手（依据第三轮分桌记录）
            assignments = TableAssignment.query.filter_by(round_number=3).order_by(TableAssignment.seat_number).all()
            remaining_data = [{
                'unique_id': a.player.unique_id,
                'name': a.player.name,
                'score': a.player.score_round3
            } for a in assignments]

            # 合并两部分，再按分数降序排序
            combined = eliminated_data + remaining_data
            combined.sort(key=lambda x: x['score'], reverse=True)

            return render_template('scoreboard.html', scoreboard=combined, round_number=3)

    else:
        flash("无效轮次")
        return redirect(url_for('index'))
    return render_template('scoreboard.html', 
                           scoreboard=scoreboard_data, 
                           round_number=round_number,
                           title=title)


# ---------- 第三轮淘汰记录 --------------

# @app.route('/round3/elimination', methods=['GET', 'POST'])
# def round3_elimination():
#     # 限定必须是裁判登录
#     if 'judge' not in session:
#         flash("请先登录裁判账号")
#         return redirect(url_for('judge_login'))

#     if request.method == 'POST':
#         # 获取淘汰选手的唯一编号
#         player_unique_id = request.form['player_unique_id'].strip()
#         player = Player.query.filter_by(unique_id=player_unique_id).first()
#         if not player:
#             flash("找不到该选手")
#             return redirect(url_for('round3_elimination'))

#         # 获取当前第三轮淘汰记录数，确定淘汰顺序
#         current_eliminations = Elimination.query.filter_by(round_number=3).count()
#         elimination_order = current_eliminations + 1

#         # 计算固定得分，根据淘汰顺序
#         fixed_score = calculate_elimination_score(elimination_order)

#         # 创建淘汰记录（Elimination 模型中建议增加 round_number 和 score 字段）
#         elimination = Elimination(
#             player_id=player.id,
#             elimination_order=elimination_order,
#             round_number=3,
#             score=fixed_score
#         )
#         db.session.add(elimination)

#         # 更新该选手的第三轮积分为固定得分
#         player.score_round3 = fixed_score
#         db.session.commit()
#         flash(f"记录淘汰：选手 {player.unique_id} - {player.name}，获得 {fixed_score} 分")
#         return redirect(url_for('round3_elimination'))

#     # GET：显示淘汰记录列表（包括已经淘汰的选手）
#     eliminations = Elimination.query.filter_by(round_number=3).order_by(Elimination.elimination_order).all()
#     elimination_list = [{
#         'order': e.elimination_order,
#         'unique_id': e.player.unique_id,
#         'name': e.player.name,
#         'score': e.score
#     } for e in eliminations]
#     return render_template('round3_elimination.html', eliminations=elimination_list)




# 批量创建裁判账号（示例： judge001~judge020）
@app.route('/create_judges')
def create_judges():
    created = 0
    for i in range(1, 21):
        username = f"judge{str(i).zfill(3)}"
        if not Judge.query.filter_by(username=username).first():
            pwd = "password"
            new_judge = Judge(username=username, password=pwd)
            db.session.add(new_judge)
            created += 1
    db.session.commit()
    flash(f"成功创建 {created} 个裁判账号")
    return redirect(url_for('judge_dashboard'))

# 清空数据（仅超级裁判可用）
@app.route('/clear_data', methods=['POST'])
def clear_data():
    if 'judge' not in session or session['judge'] != 'judge044':
        flash("无权限执行该操作")
        return redirect(url_for('judge_dashboard'))

    # 清空数据逻辑
    db.session.query(TableAssignment).delete()
    db.session.query(Player).delete()
    db.session.query(Elimination).delete()
    db.session.query(JudgeSubmission).delete()
    # 删除除超级裁判之外的裁判账号
    Judge.query.filter(Judge.username != 'judge044').delete()

    db.session.commit()

    flash("✅ 数据已清空")
    return redirect(url_for('judge_dashboard'))


@app.route('/generate_players_excel', methods=['POST'])
def generate_players_excel():
    try:
        count = int(request.form['count'])
        data = []
        for i in range(count):
            name = f"选手{i+1}"
            phone = f"1{random.randint(3000000000, 9999999999)}"
            data.append({"姓名": name, "手机号": phone})
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        return send_file(output, download_name="选手信息.xlsx", as_attachment=True)
    except Exception as e:
        flash("生成失败：" + str(e))
        return redirect(url_for('index'))


if __name__ == "__main__":
    app.run(debug=True)




