import csv
import os

from fastapi import FastAPI, HTTPException, Depends, status
from sqlalchemy import create_engine, Column, Integer, String, func, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from fastapi.security import OAuth2PasswordBearer

load_dotenv()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    read_only = Column(Boolean, default=False)


class Student(Base):
    __tablename__ = 'students'

    id = Column(Integer, primary_key=True, autoincrement=True)
    last_name = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    faculty = Column(String, nullable=False)
    course = Column(String, nullable=False)
    grade = Column(Integer, nullable=False)


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    read_only: bool = False


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    read_only: Optional[bool] = False


class StudentCreate(BaseModel):
    last_name: str
    first_name: str
    faculty: str
    course: str
    grade: int


class StudentUpdate(BaseModel):
    last_name: str = None
    first_name: str = None
    faculty: str = None
    course: str = None
    grade: int = None


engine = create_engine('sqlite:///students.db')
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username, read_only=payload.get("read_only", False))
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_write_access(current_user: User = Depends(get_current_active_user)):
    if current_user.read_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read-only users cannot perform this action"
        )
    return current_user


class StudentManager:
    def __init__(self, db: Session):
        self.db = db

    def insert_student(self, last_name: str, first_name: str, faculty: str, course: str, grade: int):
        student = Student(
            last_name=last_name,
            first_name=first_name,
            faculty=faculty,
            course=course,
            grade=grade
        )
        self.db.add(student)
        self.db.commit()
        self.db.refresh(student)
        return student

    def get_all_students(self):
        return self.db.query(Student).all()

    def get_student_by_id(self, student_id: int):
        return self.db.query(Student).filter(Student.id == student_id).first()

    def update_student(self, student_id: int, student_data: StudentUpdate):
        student = self.db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return None

        update_data = student_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(student, field, value)

        self.db.commit()
        self.db.refresh(student)
        return student

    def delete_student(self, student_id: int):
        student = self.db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return False

        self.db.delete(student)
        self.db.commit()
        return True

    def load_from_csv(self, file_path: str):
        with open(file_path, 'r', encoding='utf-8') as file:
            next(file)
            reader = csv.reader(file)

            for row in reader:
                grade = int(row[5]) if row[5].isdigit() else 0

                student = Student(
                    last_name=row[1],
                    first_name=row[2],
                    faculty=row[3],
                    course=row[4],
                    grade=grade
                )
                self.db.add(student)

            self.db.commit()

    def get_students_by_faculty(self, faculty_name: str):
        return self.db.query(Student).filter(Student.faculty == faculty_name).all()

    def get_unique_courses(self):
        courses = self.db.query(Student.course).distinct().all()
        return [course[0] for course in courses]

    def get_average_grade_by_faculty(self, faculty_name: str):
        result = self.db.query(
            func.avg(Student.grade).label('average_grade')
        ).filter(Student.faculty == faculty_name).first()

        return result[0] if result[0] else 0

    def get_students_by_course_with_low_grade(self, course_name: str, max_grade: int = 30):
        return self.db.query(Student).filter(
            Student.course == course_name,
            Student.grade < max_grade
        ).all()


@app.post("/auth/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(
        (User.username == user.username) | (User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )

    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        read_only=user.read_only
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username, "read_only": db_user.read_only},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/auth/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "read_only": user.read_only},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/auth/logout")
def logout(current_user: User = Depends(get_current_active_user)):
    return {"message": "Successfully logged out"}


@app.post("/students/")
def create_student(
        student: StudentCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_write_access)
):
    manager = StudentManager(db)
    return manager.insert_student(
        last_name=student.last_name,
        first_name=student.first_name,
        faculty=student.faculty,
        course=student.course,
        grade=student.grade
    )


@app.get("/students/")
def read_all_students(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    manager = StudentManager(db)
    return manager.get_all_students()


@app.get("/students/{student_id}")
def read_student(
        student_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    manager = StudentManager(db)
    student = manager.get_student_by_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@app.put("/students/{student_id}")
def update_student(
        student_id: int,
        student: StudentUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_write_access)
):
    manager = StudentManager(db)
    updated_student = manager.update_student(student_id, student)
    if not updated_student:
        raise HTTPException(status_code=404, detail="Student not found")
    return updated_student


@app.delete("/students/{student_id}")
def delete_student(
        student_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_write_access)
):
    manager = StudentManager(db)
    success = manager.delete_student(student_id)
    if not success:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"message": "Student deleted successfully"}


@app.get("/students/faculty/{faculty_name}")
def get_students_by_faculty(
        faculty_name: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    manager = StudentManager(db)
    return manager.get_students_by_faculty(faculty_name)


@app.get("/courses/")
def get_unique_courses(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    manager = StudentManager(db)
    return manager.get_unique_courses()


@app.get("/faculty/{faculty_name}/average-grade")
def get_average_grade_by_faculty(
        faculty_name: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    manager = StudentManager(db)
    return {"faculty": faculty_name, "average_grade": manager.get_average_grade_by_faculty(faculty_name)}


@app.get("/courses/{course_name}/low-grades")
def get_students_with_low_grades(
        course_name: str,
        max_grade: int = 30,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    manager = StudentManager(db)
    return manager.get_students_by_course_with_low_grade(course_name, max_grade)


@app.post("/load-csv/")
def load_csv_data(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_write_access)
):
    manager = StudentManager(db)
    manager.load_from_csv('students.csv')
    return {"message": "CSV data loaded successfully"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST"), port=int(os.getenv("PORT")))
