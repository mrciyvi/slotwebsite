"""
🃏 Poker Game Server - Python Socket.io
დაჰოსტე Render.com ან Railway.app-ზე
"""

from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms
from flask_cors import CORS
import json
from datetime import datetime
import random
import os

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'poker-secret-2024'
socketio = SocketIO(app, cors_allowed_origins="*")

def generate_deck():
    """დეკი შევქმნა"""
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    suits = ['♠', '♥', '♦', '♣']
    deck = [rank + suit for rank in ranks for suit in suits]
    random.shuffle(deck)
    return deck

# 🎮 თამაშის მდგომარეობა
game_state = {
    'players': ['', '', '', ''],
    'playerIds': ['', '', '', ''],
    'playerBalances': [0, 0, 0, 0],
    'phase': 'waiting',  # waiting, preflop, flop, turn, river, showdown
    'pot': 0,
    'community': [],
    'dealer': 0,
    'currentPlayer': 0,
    'currentBet': 0,
    'bets': [0, 0, 0, 0],
    'folded': [False, False, False, False],
    'allIn': [False, False, False, False],
    'deck': [],
    'roundActive': False,
    'lastUpdate': datetime.now().isoformat()
}

def generate_hand():
    """2 ბილეთი რომელიმე მოთამაშისთვის"""
    if len(game_state['deck']) < 7:
        game_state['deck'] = generate_deck()
    hand = [game_state['deck'].pop(), game_state['deck'].pop()]
    return hand

def next_player():
    """შემდეგი აქტიური მოთამაშე"""
    starting_player = game_state['currentPlayer']
    
    while True:
        game_state['currentPlayer'] = (game_state['currentPlayer'] + 1) % 4
        
        if (game_state['players'][game_state['currentPlayer']] and 
            not game_state['folded'][game_state['currentPlayer']]):
            break
        
        if game_state['currentPlayer'] == starting_player:
            break
    
    return game_state['currentPlayer']

def broadcast_state():
    """ყველას გაგზავნი თამაშის მდგომარეობა"""
    socketio.emit('game_state_update', {
        'players': game_state['players'],
        'pot': game_state['pot'],
        'phase': game_state['phase'],
        'community': game_state['community'],
        'currentPlayer': game_state['currentPlayer'],
        'bets': game_state['bets'],
        'folded': game_state['folded'],
        'allIn': game_state['allIn'],
        'currentBet': game_state['currentBet'],
        'balances': game_state['playerBalances'],
        'timestamp': datetime.now().isoformat()
    }, to='poker_room')

def generate_card():
    """ერთი ბილეთი"""
    if not game_state['deck']:
        game_state['deck'] = generate_deck()
    return game_state['deck'].pop()

# ========== ROUTES ==========

@app.route('/')
def health():
    """Health check"""
    return jsonify({'status': '✅ Server კარგი', 'version': '1.0'}), 200

@app.route('/api/status')
def status():
    """თამაშის სტატუსი"""
    return jsonify({
        'game_state': game_state,
        'active_players': len([p for p in game_state['players'] if p]),
        'timestamp': datetime.now().isoformat()
    }), 200

# ========== SOCKET EVENTS ==========

@socketio.on('connect')
def handle_connect():
    """მოთამაშე კავშირდება"""
    print(f"✅ მოთამაშე დაკავშირდა: {request.sid}")
    join_room('poker_room')
    emit('connected', {'message': 'Server-თან დაკავშირდა'})

@socketio.on('disconnect')
def handle_disconnect():
    """მოთამაშე გავის"""
    print(f"👋 მოთამაშე წავიდა: {request.sid}")
    # იპოვნი ადგილი და დაა­­ტოვე
    for i, pid in enumerate(game_state['playerIds']):
        if pid == request.sid:
            game_state['players'][i] = ''
            game_state['playerIds'][i] = ''
            game_state['playerBalances'][i] = 0
            game_state['folded'][i] = False
            game_state['allIn'][i] = False
            break
    
    broadcast_state()

@socketio.on('join_seat')
def handle_join_seat(data):
    """მოთამაშე მაგიდას შედის"""
    try:
        seat = int(data['seat'])
        name = str(data['name']).strip()[:20]
        balance = float(data['balance'])
        
        if seat < 0 or seat > 3:
            emit('error', {'message': 'ადგილი არ არსებობს'})
            return
        
        if game_state['players'][seat]:
            emit('error', {'message': 'ეს ადგილი დაკავებულია'})
            return
        
        # კიდე დაბრუნებული არაა თამაში?
        game_state['players'][seat] = name
        game_state['playerIds'][seat] = request.sid
        game_state['playerBalances'][seat] = balance
        
        print(f"✅ {name} შეუერთდა ადგილი {seat+1}")
        broadcast_state()
        emit('seat_joined', {'seat': seat})
        
    except Exception as e:
        print(f"❌ Join error: {e}")
        emit('error', {'message': str(e)})

@socketio.on('leave_table')
def handle_leave_table():
    """მოთამაშე მაგიდას ტოვებს"""
    for i, pid in enumerate(game_state['playerIds']):
        if pid == request.sid:
            game_state['players'][i] = ''
            game_state['playerIds'][i] = ''
            print(f"👋 მოთამაშე წავიდა ადგილი {i+1}")
            break
    
    broadcast_state()

@socketio.on('start_round')
def handle_start_round():
    """ახალი რაუند იწყება"""
    try:
        active_players = [i for i in range(4) if game_state['players'][i]]
        
        if len(active_players) < 2:
            emit('error', {'message': 'მინიმუმ 2 მოთამაშე!!!'})
            return
        
        # დეკი შევქმნა
        game_state['deck'] = generate_deck()
        
        # მხეები დანიშნა
        game_state['dealer'] = active_players[0]
        small_blind = active_players[1] if len(active_players) > 1 else active_players[0]
        big_blind = active_players[0] if len(active_players) > 1 else active_players[1]
        
        # თამაში დაიწყო
        game_state['phase'] = 'preflop'
        game_state['pot'] = 0
        game_state['bets'] = [0, 0, 0, 0]
        game_state['folded'] = [False, False, False, False]
        game_state['allIn'] = [False, False, False, False]
        game_state['community'] = []
        game_state['currentBet'] = 100
        game_state['roundActive'] = True
        
        # Blind-ი დააგდე
        game_state['bets'][small_blind] = 50
        game_state['bets'][big_blind] = 100
        game_state['pot'] = 150
        game_state['playerBalances'][small_blind] -= 50
        game_state['playerBalances'][big_blind] -= 100
        
        # პირველი მოთამაშე ქმედებას ელოდება
        game_state['currentPlayer'] = (big_blind + 1) % 4
        while not game_state['players'][game_state['currentPlayer']]:
            game_state['currentPlayer'] = (game_state['currentPlayer'] + 1) % 4
        
        print(f"🎯 რაუند დაიწყო. პირველი მოთამაშე: {game_state['currentPlayer']}")
        
        # დეთ ხელი თითოეულ აქტიურ მოთამაშეს
        player_hands = {}
        for i in active_players:
            hand = [generate_card(), generate_card()]
            player_hands[i] = hand
            # Emit თითოეულ მოთამაშეს მის ხელი პირადად
            socketio.emit('my_hand', {'hand': hand}, to=game_state['playerIds'][i])
        
        broadcast_state()
        
    except Exception as e:
        print(f"❌ Start error: {e}")
        emit('error', {'message': str(e)})

@socketio.on('player_action')
def handle_player_action(data):
    """მოთამაშის მოქმედება (call, raise, fold, allin)"""
    try:
        seat = int(data['seat'])
        action = str(data['action']).lower()
        amount = float(data.get('amount', 0))
        
        # უსაფრთხოების შემოწმება
        if seat != game_state['currentPlayer']:
            emit('error', {'message': 'ეს არ არის თქვენი ქმედება!'})
            return
        
        if game_state['folded'][seat] or not game_state['players'][seat]:
            emit('error', {'message': 'თქვენ ვერ ქმედობთ'})
            return
        
        balance = game_state['playerBalances'][seat]
        
        # მოქმედება განახორციელე
        if action == 'fold':
            game_state['folded'][seat] = True
            print(f"📋 {game_state['players'][seat]} Fold-ი")
            
        elif action == 'check':
            if game_state['bets'][seat] < game_state['currentBet']:
                emit('error', {'message': 'Check-ი გაუქმელია, უნდა call ან raise'})
                return
            print(f"✓ {game_state['players'][seat]} Check-ი")
            
        elif action == 'call':
            needed = game_state['currentBet'] - game_state['bets'][seat]
            if balance < needed:
                emit('error', {'message': 'არასაკმარისი ბალანსი'})
                return
            game_state['bets'][seat] += needed
            game_state['pot'] += needed
            game_state['playerBalances'][seat] -= needed
            print(f"📞 {game_state['players'][seat]} Call-ი ${needed}")
            
        elif action == 'raise':
            if amount <= game_state['currentBet']:
                emit('error', {'message': f'Raise უნდა იყოს >{game_state["currentBet"]}'})
                return
            if balance < amount:
                emit('error', {'message': 'არასაკმარისი ბალანსი'})
                return
            game_state['bets'][seat] = amount
            game_state['pot'] += amount
            game_state['playerBalances'][seat] -= amount
            game_state['currentBet'] = amount
            print(f"📈 {game_state['players'][seat]} Raise-ი ${amount}")
            
        elif action == 'allin':
            all_chips = balance
            if all_chips > 0:
                game_state['bets'][seat] += all_chips
                game_state['pot'] += all_chips
                game_state['playerBalances'][seat] = 0
                game_state['allIn'][seat] = True
                if all_chips > game_state['currentBet']:
                    game_state['currentBet'] = all_chips
            print(f"💥 {game_state['players'][seat]} All In-ი!")
        
        # შემდეგი მოთამაშე
        next_player()
        broadcast_state()
        
    except Exception as e:
        print(f"❌ Action error: {e}")
        emit('error', {'message': str(e)})

@socketio.on('next_phase')
def handle_next_phase():
    """მომდევნო ფაზე (flop, turn, river, showdown)"""
    try:
        phase_order = ['preflop', 'flop', 'turn', 'river', 'showdown']
        current_idx = phase_order.index(game_state['phase'])
        
        if current_idx < len(phase_order) - 1:
            game_state['phase'] = phase_order[current_idx + 1]
            
            if game_state['phase'] == 'flop':
                game_state['community'] = [
                    generate_card(), generate_card(), generate_card()
                ]
            elif game_state['phase'] in ['turn', 'river']:
                game_state['community'].append(generate_card())
            
            # ბეთი გახსნა
            game_state['currentBet'] = 0
            game_state['bets'] = [0, 0, 0, 0]
            
            # ახალი მოთამაშე დაიწყოს
            for i in range(4):
                if game_state['players'][i] and not game_state['folded'][i]:
                    game_state['currentPlayer'] = i
                    break
            
            print(f"📊 ფაზე: {game_state['phase']}")
        
        broadcast_state()
        
    except Exception as e:
        print(f"❌ Phase error: {e}")

@socketio.on('end_round')
def handle_end_round(data):
    """რაუند დაასრულე და შედეგი გამოთვლი"""
    try:
        # აქ უნდა შედეგი გამოთვალო
        # უმარტივეს ვერსია: გამარჯვებული არის უკანსკით დარჩენილი ან closest hand
        
        active_players = [i for i in range(4) 
                         if game_state['players'][i] and not game_state['folded'][i]]
        
        if len(active_players) == 1:
            winner = active_players[0]
        else:
            # Simple: თუ რამდენი chip აქვს (უმარტივე აღრიცხვა)
            winner = max(active_players, key=lambda i: game_state['playerBalances'][i])
        
        # შემოსავალი
        game_state['playerBalances'][winner] += game_state['pot']
        
        print(f"🏆 გამარჯვებული: {game_state['players'][winner]}")
        
        # რაუند დასრულება
        game_state['phase'] = 'waiting'
        game_state['roundActive'] = False
        game_state['pot'] = 0
        
        broadcast_state()
        emit('round_ended', {
            'winner': game_state['players'][winner],
            'winAmount': game_state['pot']
        }, to='poker_room')
        
    except Exception as e:
        print(f"❌ End round error: {e}")
        emit('error', {'message': str(e)})

# ========== RUN ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
