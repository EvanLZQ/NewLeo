from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def upload_image(request):
    if request.method == 'POST':
        image_file = request.FILES.get('file')
        # handle uploaded file
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})
