from flask_wtf import FlaskForm
from flask_wtf.file import MultipleFileField
from wtforms import StringField, TextAreaField, IntegerField, SelectField, BooleanField, PasswordField
from wtforms.validators import DataRequired, NumberRange


class DishForm(FlaskForm):
    title = StringField('Название блюда', validators=[DataRequired()])
    description = TextAreaField('Описание', validators=[DataRequired()])
    cooking_time = IntegerField('Время приготовления (мин)', validators=[DataRequired(), NumberRange(min=1)])
    servings = IntegerField('Порции', validators=[DataRequired(), NumberRange(min=1)])
    ingredients = TextAreaField('Ингредиенты', validators=[DataRequired()])
    steps = TextAreaField('Шаги приготовления', validators=[DataRequired()])
    photos = MultipleFileField('Фотографии')


class FeedbackForm(FlaskForm):
    rating = SelectField(
        'Оценка',
        choices=[
            (5, 'отлично'),
            (4, 'хорошо'),
            (3, 'удовлетворительно'),
            (2, 'неудовлетворительно'),
            (1, 'плохо'),
            (0, 'ужасно')
        ],
        coerce=int,
        default=5
    )
    comment = TextAreaField('Текст отзыва', validators=[DataRequired()])


class AuthForm(FlaskForm):
    username = StringField('Логин', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember_me = BooleanField('Запомнить меня')


class RegisterForm(FlaskForm):
    username = StringField('Логин', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    last_name = StringField('Фамилия', validators=[DataRequired()])
    first_name = StringField('Имя', validators=[DataRequired()])
    middle_name = StringField('Отчество')
    role_id = SelectField('Роль', coerce=int, validators=[DataRequired()]) 