from openai import OpenAI
client = OpenAI()

vector_store = client.vector_stores.create(        # Create vector store
    name="Yuhniverse",
)

client.vector_stores.files.upload_and_poll(        # Upload file
    vector_store_id=vector_store.id,
    file=open("/Users/y_anaray/Downloads/Day_Dream_CAPSTONE/Investment product masterfile/Investment products_Masterfile_v69.csv", "rb")
)