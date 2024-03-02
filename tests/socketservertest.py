import socket


# * Table
# *1 (Temporary)

def authenticate(password):
    correct_password = "secret_password"  # Hardcoded*1 password
    return password == correct_password

def run_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_ip = "127.0.0.1"
    port =  6765
    server.bind((server_ip, port))
    server.listen(0)
    print(f"Listening on {server_ip}:{port}")

    while True:
        try:
            client_socket, client_address = server.accept()
            print(f"Accepted connection from {client_address[0]}:{client_address[1]}")

            # Authentication phase
            client_socket.send("Password required.".encode("utf-8"))
            password = client_socket.recv(1024).decode("utf-8").strip()
            if not authenticate(password):
                client_socket.send("Authentication failed.".encode("utf-8"))
                client_socket.close()
                continue  # Continue to the next iteration of the loop to accept new connections

            client_socket.send("Authentication successful.".encode("utf-8"))

            # Communication phase
            while True:
                try:
                    request = client_socket.recv(1024)
                    if not request:
                        break  # Client has closed the connection
                    request = request.decode("utf-8")

                    #example eas code

                    # Splitting the string at each space
                    split_strings = request.split()

                    command = split_strings[0]
                    if command == "sendAlert":
                        org = split_strings[1]
                        type = split_strings[2]
                        countycodes = split_strings[3]
                        exp = split_strings[4]
                        jjjhhmm = split_strings[5]
                        station = split_strings[6]
                        EAS_string = f"ZCZC-{org}-{type}-{countycodes}+{exp}-{jjjhhmm}-{station}-"

                        # if this code was in ASMARA, about now, it would gen a header and run a local alert!

                        # run a check here

                        # Example sendAlert command
                        #sendAlert EAS DMO 00000 0015 0200820 WABC/FM
                        
                        response = "Sent!".encode("utf-8") # do not remove this or else server will think 500 internal error
                        client_socket.send(response)

                        #if not sent, send this
                        #response = "Failed to Send Alert".encode("utf-8")
                        #client_socket.send(response)                        


                    else:
                        response = "Command Not Found".encode("utf-8")
                        client_socket.send(response)



                    # Printing the list of substrings

                    #print(f"Received: {request}")
                    #response = "Message received".encode("utf-8")
                    #client_socket.send(response)
                    #client_socket.close()
                        
                    client_socket.close()
                    print("Connection to client closed")
                except socket.error as e:
                    print(f"Socket error: {e}") # might print out socket error 9, this is good
                    break  # Break the loop if there's an error


        except socket.error as e:
            print(f"Socket error: {e}")
            break  # Break the loop if there's an error

    server.close()



run_server()