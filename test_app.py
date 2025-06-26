import pytest
from app import app, db
from models import Account, UserRole, Dish, Feedback
from flask import url_for

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            # Создаем роли
            admin_role = UserRole(name='Администратор', description='Админ')
            user_role = UserRole(name='Пользователь', description='Обычный пользователь')
            db.session.add_all([admin_role, user_role])
            db.session.commit()
        yield client
        with app.app_context():
            db.drop_all()

def register(client, username, password, role_id=2):
    return client.post('/register', data={
        'username': username,
        'password': password,
        'last_name': 'Тестов',
        'first_name': 'Тест',
        'middle_name': '',
        'role_id': role_id
    }, follow_redirects=True)

def login(client, username, password):
    return client.post('/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)

def add_recipe(client, token=None):
    data = {
        'title': 'Тестовый рецепт',
        'description': 'Описание',
        'cooking_time': 30,
        'servings': 2,
        'ingredients': 'Ингредиенты',
        'steps': 'Шаги'
    }
    return client.post('/create-dish', data=data, follow_redirects=True)

def add_feedback(client, recipe_id, rating=5, comment='Отлично!'):
    return client.post(f'/dish/{recipe_id}/add-feedback', data={
        'rating': rating,
        'comment': comment
    }, follow_redirects=True)

def logout(client):
    return client.get('/logout', follow_redirects=True)

def test_register_and_login(client):
    rv = register(client, 'user1', 'pass1')
    assert 'Регистрация успешна' in rv.data.decode('utf-8')
    rv = login(client, 'user1', 'pass1')
    assert 'Выйти' in rv.data.decode('utf-8')

def test_register_admin(client):
    rv = register(client, 'admin1', 'adminpass', role_id=1)
    assert 'Регистрация успешна' in rv.data.decode('utf-8')

def test_login_wrong_password(client):
    register(client, 'user2', 'pass2')
    rv = login(client, 'user2', 'wrong')
    assert 'Невозможно аутентифицироваться' in rv.data.decode('utf-8') or 'Неверный логин или пароль' in rv.data.decode('utf-8')

def test_add_recipe(client):
    register(client, 'user3', 'pass3')
    login(client, 'user3', 'pass3')
    rv = add_recipe(client)
    assert 'Блюдо успешно добавлено' in rv.data.decode('utf-8')

def test_add_recipe_unauth(client):
    rv = add_recipe(client)
    assert 'Для выполнения данного действия необходимо пройти процедуру аутентификации' in rv.data.decode('utf-8')

def test_view_recipe(client):
    register(client, 'user4', 'pass4')
    login(client, 'user4', 'pass4')
    add_recipe(client)
    rv = client.get('/')
    assert 'Тестовый рецепт' in rv.data.decode('utf-8')

def test_edit_recipe_rights(client):
    register(client, 'user5', 'pass5')
    login(client, 'user5', 'pass5')
    add_recipe(client)
    rv = client.get('/edit-dish/1')
    assert 'Редактировать блюдо' in rv.data.decode('utf-8')
    logout(client)
    register(client, 'user6', 'pass6')
    login(client, 'user6', 'pass6')
    rv = client.get('/edit-dish/1', follow_redirects=True)
    assert 'У вас недостаточно прав' in rv.data.decode('utf-8')

def test_delete_recipe_rights(client):
    register(client, 'user7', 'pass7')
    login(client, 'user7', 'pass7')
    add_recipe(client)
    rv = client.post('/delete-dish/1', follow_redirects=True)
    assert 'Блюдо успешно удалено' in rv.data.decode('utf-8')
    add_recipe(client)
    logout(client)
    register(client, 'user8', 'pass8')
    login(client, 'user8', 'pass8')
    rv = client.post('/delete-dish/2', follow_redirects=True)
    assert 'У вас недостаточно прав' in rv.data.decode('utf-8')

def test_admin_can_edit_delete_any_recipe(client):
    register(client, 'admin2', 'adminpass2', role_id=1)
    login(client, 'admin2', 'adminpass2')
    add_recipe(client)
    logout(client)
    register(client, 'user9', 'pass9')
    login(client, 'user9', 'pass9')
    add_recipe(client)
    logout(client)
    login(client, 'admin2', 'adminpass2')
    rv = client.get('/edit-dish/2')
    assert 'Редактировать блюдо' in rv.data.decode('utf-8')
    rv = client.post('/delete-dish/2', follow_redirects=True)
    assert 'Блюдо успешно удалено' in rv.data.decode('utf-8')

def test_add_feedback(client):
    register(client, 'user10', 'pass10')
    login(client, 'user10', 'pass10')
    add_recipe(client)
    rv = add_feedback(client, 1)
    assert 'Отзыв успешно добавлен' in rv.data.decode('utf-8')

def test_add_feedback_twice(client):
    register(client, 'user11', 'pass11')
    login(client, 'user11', 'pass11')
    add_recipe(client)
    add_feedback(client, 1)
    rv = add_feedback(client, 1)
    assert 'Вы уже оставляли отзыв' in rv.data.decode('utf-8')

def test_feedback_unauth(client):
    register(client, 'user12', 'pass12')
    login(client, 'user12', 'pass12')
    add_recipe(client)
    logout(client)
    rv = add_feedback(client, 1)
    assert 'Для выполнения данного действия необходимо пройти процедуру аутентификации' in rv.data.decode('utf-8')

def test_pagination(client):
    register(client, 'user13', 'pass13')
    login(client, 'user13', 'pass13')
    for i in range(12):
        client.post('/create-dish', data={
            'title': f'Рецепт {i}',
            'description': 'Описание',
            'cooking_time': 10,
            'servings': 1,
            'ingredients': 'Ингредиенты',
            'steps': 'Шаги'
        }, follow_redirects=True)
    rv = client.get('/')
    assert 'Рецепт 0' in rv.data.decode('utf-8') and 'Рецепт 10' not in rv.data.decode('utf-8')
    rv = client.get('/?page=2')
    assert 'Рецепт 10' in rv.data.decode('utf-8')

def test_logout(client):
    register(client, 'user14', 'pass14')
    login(client, 'user14', 'pass14')
    rv = logout(client)
    assert 'Войти' in rv.data.decode('utf-8')

def test_access_control(client):
    rv = add_recipe(client)
    assert 'Для выполнения данного действия необходимо пройти процедуру аутентификации' in rv.data.decode('utf-8')
    rv = client.get('/edit-dish/1', follow_redirects=True)
    assert 'Для выполнения данного действия необходимо пройти процедуру аутентификации' in rv.data.decode('utf-8')

def test_markdown_rendering(client):
    register(client, 'user15', 'pass15')
    login(client, 'user15', 'pass15')
    client.post('/create-dish', data={
        'title': 'MD',
        'description': '# Заголовок',
        'cooking_time': 10,
        'servings': 1,
        'ingredients': '* item',
        'steps': '**bold**'
    }, follow_redirects=True)
    rv = client.get('/')
    assert 'MD' in rv.data.decode('utf-8')
    rv = client.get('/dish/1')
    assert '<h1>Заголовок' in rv.data.decode('utf-8') or '<li>item' in rv.data.decode('utf-8') or '<strong>bold' in rv.data.decode('utf-8') 