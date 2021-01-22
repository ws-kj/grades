import sqlite3, string, collections, os
import discord
from discord.ext import commands
from studentvue import StudentVue
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from prettytable import PrettyTable


load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
KEY = os.getenv('KEY')

f = Fernet(KEY)

bot = commands.Bot(command_prefix='g!')

root = os.path.dirname(os.path.realpath(__file__))

#---------------------------------------------------------------------

def dict_gen(curs):
    # From Python Essential Reference by David Beazley
    field_names = [d[0].lower() for d in curs.description]
    while True:
        rows = curs.fetchmany()
        if not rows: return
        for row in rows:
            yield dict(zip(field_names, row))

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db():
    return sqlite3.connect(root + "/grades.db")

def commit(db, q, *args):
    c = db.cursor()
    c.execute(q, args);
    r = c.lastrowid
    db.commit()
    return r

# code by Niles Rogoff. Thanks man!
def _make_valid_ident(i):
	if i[0] not in (string.ascii_letters + "_"):
		i = "sql_" + i[0]
	return "".join([c if c in (string.ascii_letters + string.digits + "_") else "_" for c in i])

def _try_symbolize_names_for_sql(l):
	l = {_make_valid_ident(k): v for k, v in l.items()}
	cls = collections.namedtuple("t", l.keys())
	old_getitem = cls.__getitem__
	cls.__getitem__ = lambda self, k: l[k] if isinstance(k, str) else old_getitem(self, k)
	return cls(**l)


def nquery(q, *args, symbolize_names =  True):
    db = get_db()
    c = db.cursor()
    c.execute(q, args) # no splat!
    return [(_try_symbolize_names_for_sql if symbolize_names else lambda i: i)({c.description[i][0]: v for i, v in enumerate(row)}) for row in c.fetchall()]

def query(q, *args):
    db = get_db()
    c = db.cursor()
    rows = [r for r in dict_gen(c.execute(q, args))]
    db.commit()
    db.close()
    return rows

def execute(q, *args):
    db = get_db()
    c = db.cursor()
    c.execute(q, args)
    db.commit()
    db.close()

def init_db():
    db = get_db()
    db.row_factory = dict_factory
    c = db.cursor()

    c.execute("""
    create table if not exists users (
        id integer text not null,
        username text not null,
        password text not null,
        domain text not null
    )
    """)

    db.commit()
    db.close()

#---------------------------------------------------------------------

init_db()


@bot.command(name='get')
async def get(ctx):
    q = query("""select * from users where id == ?""", ctx.message.author.id)
    if len(q) == 0:
        await setup_b(ctx, ctx.message.author)
        return

    u = q[0]['username']
    p = f.decrypt(q[0]['password']).decode()
    d = q[0]['domain']
    sv = StudentVue(u, p, d)
    
    gb = sv.get_gradebook(1)['Gradebook']['Courses']['Course']
    
    grades=[]

    for t in gb:
        vals = ['', '', '']
        for key, value in t.items():
            if key == '@Title':
                vals[0] = value
            if key == 'Marks':
                for i in value['Mark']:
                    nextent = False
                    for j in i.items():
                        if j[0] == '@MarkName' and j[1][: 2] == 'MP':
                            nextent = True

                        if nextent:
                            if j[0] == '@CalculatedScoreString':
                                vals[1] = j[1]
                            if j[0] == '@CalculatedScoreRaw':
                                vals[2] = j[1]
                                nextent = False
        grades.append(vals)

    res = "```Your Grades:\n"

    table = PrettyTable()
    table.field_names = ["Class", "Letter Grade", "Exact Grade"]

    for a in grades:
        table.add_row(a)

    table.align = "l"

    res += str(table)
    
    res += "```"

    await ctx.send(res)

@bot.command(name='setup')
async def setup_c(ctx):
    await setup_b(ctx, ctx.message.author)

@bot.command()
async def setup_b(ctx, user: discord.Member = None,  message=None):
    if user is None:
        await ctx.send("no user")
    else:
        await user.send("Please enter 'g!creds' followed by your StudentVUE username, password, and domain seperated by spaces.\n Example: `g!creds 000000 pass.word00 vue.myschool.us`:")

@bot.command(name='creds')
async def creds(ctx):
    if isinstance(ctx.channel, discord.channel.DMChannel):    
        words=ctx.message.content.split()
        if len(words) < 4:
            await ctx.message.author.send("Please enter 'g!creds' followed by your StudentVUE username, password, and domain seperated by spaces.\n Example: `g!creds 000000 pass.word00 vue.myschool.us`:")
            return;

        words = words[1:4]

        uid = ctx.message.author.id;
        u = words[0]
        p = f.encrypt(words[1].encode())
        d = words[2]

        execute("""delete from users where id == ?""", uid)

        execute("""insert into users (id, username, password, domain) values (?, ?, ?, ?)""", uid, u, p, d)

        await ctx.message.author.send('Account setup complete. You may now use g!get to view your StudentVUE grades. Keep in mind that if your creds are incorrect, you will not be able to view your grades.')
    else:
        await ctx.send('g!creds only works in DM')
bot.run(TOKEN)
