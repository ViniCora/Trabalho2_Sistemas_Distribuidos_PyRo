import Pyro5.api
import threading
import time
import argparse
from enum import Enum

# SER UNICAST
        # (1) Segurança: no máximo um processo por vez pode ser executado na SC;
        # (2) Subsistência: os pedidos para entrar e sair de uma seção crítica precisam ser bem-sucedidos; 
        # (3) Ordenação: ordenar as mensagens que solicitarem a entrada na SC.
        
class State(Enum):
    RELEASED = 1
    HELD = 2
    WANTED = 3


nome_processo = ''
#On initialization state := RELEASED;
state = State.RELEASED
HEART_BEAT_TIME = 10
TIME_HELD_SC = 8
TIME_WAIT_SC = 5
LIST_PEERS = ['peerA', 'peerB', 'peerC']
ultima_vez_heartbeat = {}
peers_lock = threading.Lock()
fila_request = []
count_replies = 0

@Pyro5.api.expose
class Peer(object):
    @Pyro5.api.oneway
    def heart_beat(self, name):
        agora = time.time()
        ultima_vez_heartbeat[name] = agora

    @Pyro5.api.oneway
    def request_entry(self,timestamp, nome):
        print(f'Recebeu o pedido de entrada do [{nome}]')
        global state, fila_request

        # Cada peer verifica se está segurando
        if state == State.HELD:
            print(f"O {nome_processo} está em estado HELD e não pode responder a {nome} > Adicionado na Fila.")
            fila_request.append((timestamp, nome))
        elif state == State.RELEASED:
            proxy = Pyro5.api.Proxy("PYRONAME:" + nome) 
            print(f"{nome_processo} está em estado RELEASED e responde a {nome}.")
            proxy.reply_granted()
        elif state == State.WANTED:
            print('Pending')
            # Comparar timestamps
            # Se o outro for mais antigo permite
            # Se o o outro for mais recente coloca na fila


    @Pyro5.api.oneway
    def reply_granted(self):
        global count_replies
        count_replies += 1
        print(f"{nome_processo} recebeu uma permissão. Total de permissões: {count_replies} de {len(LIST_PEERS) - 1}")

    def request_SC(self):
        global state, count_replies
        state = State.WANTED
        count_replies = 0
        #segudos desde 1 de janeiro de 1970
        timestamp = time.time()
        print(f"{nome_processo} está em estado WANTED e solicita permissão para entrar na SC. ts={timestamp}")
        
        for peer in LIST_PEERS:
            if peer != nome_processo:
                try:
                    # Pede para todos para entrar na SC
                    proxy = Pyro5.api.Proxy("PYRONAME:" + peer) 
                    proxy.request_entry(timestamp, nome_processo)
                except Exception as e:
                    print(f"Falha ao enviar request_entry para {peer}: {e}")

        max_tempo_espera = time.time() + TIME_WAIT_SC
        while True:
            if count_replies == len(LIST_PEERS) - 1:
                print(f"{nome_processo} recebeu permissão de todos os peers.")
                self.enter_SC()
                break
            if time.time() > max_tempo_espera:
                #fazer a desativacao
                print(f"EXCEDEU - verificar os peers ativos e quem não respondeu - desativar ele")
                break
            time.sleep(0.1) 
        

    def enter_SC(self):
            global state
            if(state != State.HELD and count_replies == len(LIST_PEERS) - 1):
                state = State.HELD
                print(f"{nome_processo} entrou na seção crítica.")
                #########################################################################
                # Não pode ser time sleep se não eu n vou conseguir liberar a SC manualmente
                #time.sleep(TIME_HELD_SC)  # Tempo dentro da SC
                
                #Colocar uns locks
                inicio_held = time.time()
                while(State.HELD == state):            
                    if(time.time() > inicio_held + TIME_HELD_SC):
                        print(f"{nome_processo} atingiu o tempo máximo na seção crítica.")
                        self.exit_SC()
                        break
                    time.sleep(0.1)

    def exit_SC(self):
        global state, fila_request
        state = State.RELEASED
        print(f"{nome_processo} saiu da SC")

        if not fila_request:
            print("Nenhum processo aguardando a SC.")
        else:
            print(f"Processos aguardando na fila: {[req[1] for req in fila_request]}")              
        # Processa fila
        for ts, requester in fila_request:
            try:
                proxy = Pyro5.api.Proxy("PYRONAME:" + requester)
                proxy.reply_granted(nome_processo)
            except:
                print(f"Não foi possível enviar permissão para {requester}")
        #Ajustar isso para não esvaziar a fila mas ir para o próximo
        fila_request.clear()


def start_nameserver():
    ns_uri, ns_daemon, _ = Pyro5.nameserver.start_ns(host="localhost", port=9090)
    print(f"Name Server iniciado em {ns_uri}")
    ns_daemon.requestLoop()


def localizar_nameserver():
    try:
        ns = Pyro5.api.locate_ns()
    except:
        print("NS não encontrado, criando um novo...")
        t = threading.Thread(target=start_nameserver, daemon=True)
        t.start()
        ns = Pyro5.api.locate_ns()
    return ns


def iniciar_processo(processo):
    global nome_processo
    daemon = Pyro5.server.Daemon()
    ns = localizar_nameserver()
    nome_processo = processo
    uri = daemon.register(Peer)
    ns.register(nome_processo, uri)

    print(nome_processo + " Iniciado.")
    daemon.requestLoop()


def iniciar_thread_processo(nome_processo):
    t = threading.Thread(target=iniciar_processo, args=(nome_processo,))
    t.start()


def enviar_heartbeat_para_peer(peer):
    while True:
        with peers_lock:
            if peer not in LIST_PEERS:
                print(f"Peer {peer} foi removido da lista, thread de envio encerrada.")
                break

        inicio = time.time()
        try:
            object_name = "PYRONAME:" + peer
            proxy = Pyro5.api.Proxy(object_name)
            proxy.heart_beat(nome_processo)
        except Exception as e:
            print(f"Falha ao enviar heartbeat para {peer}: {e}")

        duracao = time.time() - inicio
        sleep_time = max(0.0, HEART_BEAT_TIME - duracao)
        time.sleep(sleep_time)


def iniciar_heartbeats():
    for peer in LIST_PEERS:
        if peer != nome_processo:
            t = threading.Thread(target=enviar_heartbeat_para_peer, args=(peer,), daemon=True)
            t.start()


def monitorar_peers():
    global LIST_PEERS
    while True:
        agora = time.time()
        with peers_lock:
            if ultima_vez_heartbeat:
                for peer in LIST_PEERS[:]:
                    ultimo = ultima_vez_heartbeat.get(peer, None)
                    if ultimo is not None and agora - ultimo > HEART_BEAT_TIME:
                        print(f"Peer {peer} não enviou heartbeat a mais de {HEART_BEAT_TIME}s, removendo da lista")
                        LIST_PEERS.remove(peer)
        time.sleep(0.5)

def iniciar_monitorar_peers():
    t_monitor = threading.Thread(target=monitorar_peers, daemon=True)
    t_monitor.start()


if __name__ == "__main__":
    # Configuração do argparse para receber o nome do processo
    parser = argparse.ArgumentParser()
    parser.add_argument("--nome", required=True, help="Nome do processo (peer)")
    args = parser.parse_args()
    nome_processo = args.nome

    iniciar_thread_processo(nome_processo)
    time.sleep(10)

    #iniciar_heartbeats()
    #iniciar_monitorar_peers()


    while True:
        print("1 - Requisitar recursos")
        print("2 - Liberar recursos")
        print("3 - Listar peers ativos")
        opcao = input("Selecione uma das opções: ")

        proxy = Pyro5.api.Proxy("PYRONAME:" + nome_processo)

        if opcao == '1':
            timeS = time.time()
            proxy.request_SC(timeS)

        elif opcao == '2':
            if state == State.HELD:
                print(f"{nome_processo} Liberando recursos manualmente")
                proxy.exit_SC()    
            else:
                print(f"{nome_processo} Não está na seção crítica.")
            #organizar para pegar o próximo da fila

        if opcao == '3':
            ns = Pyro5.api.locate_ns()
            objetos = ns.list()
            print("")
            print("Lista de peers ativos: ")
            for nome, uri in objetos.items():
                if nome != "Pyro.NameServer":
                    print(f"Peer ativo: {nome}")
            print("")
