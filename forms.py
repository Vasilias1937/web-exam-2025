from flask_wtf import FlaskForm
from flask_wtf.file import MultipleFileField
from wtforms import StringField, TextAreaField, IntegerField, SelectField, BooleanField, PasswordField
from wtforms.validators import DataRequired, NumberRange


class DishForm(FlaskForm):
    name = StringField('Название блюда', validators=[DataRequired()])
    details = TextAreaField('Описание', validators=[DataRequired()])
    cook_time = IntegerField('Время приготовления (мин)', validators=[DataRequired(), NumberRange(min=1)])
    portions = IntegerField('Порции', validators=[DataRequired(), NumberRange(min=1)])
    components = TextAreaField('Ингредиенты', validators=[DataRequired()])
    instructions = TextAreaField('Шаги приготовления', validators=[DataRequired()])
    photos = MultipleFileField('Фотографии')


class FeedbackForm(FlaskForm):
    score = SelectField(
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
    login = StringField('Логин', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember_me = BooleanField('Запомнить меня') 