Settings.MinSimilarity = 0.95

while True:

    if exists("connection_lost.png", 5):
        click("refresh.png")
        wait(1)

    if exists("new_chat.png", 5):
        click("new_chat.png")
        wait(1)
        if exists("submit.png"): 
            click("submit.png")
    if not exists("in_progress.png"):


            
        if exists("textbox.png", 5):
            click("textbox.png")
            type("continue iterating on the scene issues in the voxel repo.")
            click("submit.png")
            print("[ok] typed continue and submitted")
            mouseMove(Location(SCREEN.w / 2, SCREEN.h / 2))

    keyDown(Key.CTRL)

    type(Key.TAB)

    #type(Key.TAB)
    keyUp(Key.CTRL)
    wait(5)
    mouseMove(Location(SCREEN.w / 3, SCREEN.h / 3))
    wheel(WHEEL_UP, 5)