import Pyro5.api
import threading
import time

@Pyro5.api.expose
class GreetingMaker(object):
    def get_fortune(self, name):
        return "Hello, {0}. Here is your fortune message:\n" \
               "Tomorrow's lucky number is 12345678.".format(name)
               
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

def iniciar_processo():
    daemon = Pyro5.server.Daemon()
    ns = localizar_nameserver()
    processo = input("Qual o nome do processo? ").strip()    
    uri = daemon.register(GreetingMaker)
    ns.register(processo, uri)
    
    print(processo + " Iniciado.")
    daemon.requestLoop()
    
def iniciar_thread_processo():
    t = threading.Thread(target=iniciar_processo)
    t.start()

if __name__ == "__main__":
    iniciar_thread_processo()
    time.sleep(10)
    while True:
        acao_executar = input("Qual a ação? ").strip()
        object_name = "PYRONAME:" + acao_executar
        greeting_maker = Pyro5.api.Proxy(object_name)
        print(greeting_maker.get_fortune("Cliente"))
