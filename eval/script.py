with open('script.txt', 'w') as f:
    for x in range(1,21):
        for y in range(1,21):
            f.write("X[x=" + str(x) + "&y=" + str(y) + "&clk](sched,sched1)\n")

    for z in range(1,21):
        for t in range(1,21):
            f.write("X[z=" + str(z) + "&t=" + str(t) + "&!clk](sched)\n")

    for z in range(1,21):
        for t in range(1,21):
            f.write("X[z=" + str(z) + "&t=" + str(t) + "&!clk](sched1)\n")

