from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import auth, users, wallet, loans, payments, admin, products, invests, notifications, passphrase, exportdata, offers, gifts, sell_airtime, reproducts

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Merite API",
    description="A comprehensive services API with phone authentication, wallet, loans, and payment links",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(wallet.router)
app.include_router(loans.router)
app.include_router(payments.router)
app.include_router(admin.router)
app.include_router(products.router)
app.include_router(invests.router)
app.include_router(notifications.router)
app.include_router(passphrase.router)
app.include_router(exportdata.router)
app.include_router(offers.router)
app.include_router(gifts.router)
app.include_router(sell_airtime.router)
app.include_router(reproducts.router)


@app.get("/")
def root():
    return {
        "message": "Merite API",
        "version": "1.0.0",
        "endpoints": {
            "auth": "/auth",
            "users": "/users",
            "wallet": "/wallet",
            "loans": "/loans",
            "payments": "/payments",
            "notifications": "/notifications",
            "passphrase": "/passphrase",
            "exportdata": "/exportdata",
            "relworx": "/relworx",
            "docs": "/docs"
        }
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
